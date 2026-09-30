import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc, asc, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User, FuelLog, ServiceLog, ItemLocation, Task, ChatHistory


# --- Пользователи ---

async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    full_name: str,
    is_admin: bool = False
) -> User:
    """Получает пользователя по telegram_id или создает нового."""
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            is_admin=is_admin,
            last_seen_at=datetime.now()
        )
        session.add(user)
        await session.flush()
    else:
        # Обновляем имя, если изменилось
        if user.full_name != full_name:
            user.full_name = full_name
            await session.flush()

    return user


async def touch_user(session: AsyncSession, telegram_id: int) -> None:
    """Мягко обновляет время последнего визита. Ошибки не критичны."""
    stmt = (
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(last_seen_at=datetime.now())
    )
    await session.execute(stmt)


# --- Заправки (FuelLog) ---

async def add_fuel_log(
    session: AsyncSession,
    user_id: int,
    liters: float,
    cost: float,
    odometer: int,
    station_name: Optional[str] = None
) -> FuelLog:
    """Добавляет запись о заправке."""
    log = FuelLog(
        user_id=user_id,
        liters=liters,
        cost=cost,
        odometer=odometer,
        station_name=station_name,
        date=datetime.now()
    )
    session.add(log)
    await session.flush()
    return log


async def get_recent_fuel_logs(
    session: AsyncSession,
    user_id: int,
    limit: int = 5
) -> List[FuelLog]:
    """Возвращает последние записи о заправках пользователя."""
    stmt = (
        select(FuelLog)
        .where(FuelLog.user_id == user_id)
        .order_by(desc(FuelLog.date))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_last_fuel_log(
    session: AsyncSession,
    user_id: int
) -> Optional[FuelLog]:
    """Возвращает последнюю запись о заправке пользователя."""
    stmt = (
        select(FuelLog)
        .where(FuelLog.user_id == user_id)
        .order_by(desc(FuelLog.date), desc(FuelLog.id))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_last_service_log(
    session: AsyncSession,
    user_id: int
) -> Optional[ServiceLog]:
    """Возвращает последнюю запись о ТО/ремонте пользователя."""
    stmt = (
        select(ServiceLog)
        .where(ServiceLog.user_id == user_id)
        .order_by(desc(ServiceLog.date), desc(ServiceLog.id))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_fuel_stats(
    session: AsyncSession,
    user_id: int
) -> Dict[str, Any]:
    """Возвращает агрегированную статистику по заправкам."""
    stmt = select(
        func.count(FuelLog.id).label("count"),
        func.sum(FuelLog.liters).label("total_liters"),
        func.sum(FuelLog.cost).label("total_cost"),
        func.max(FuelLog.odometer).label("max_odometer")
    ).where(FuelLog.user_id == user_id)

    result = await session.execute(stmt)
    row = result.one()

    count = row.count or 0
    total_liters = row.total_liters or 0.0
    total_cost = row.total_cost or 0.0
    max_odometer = row.max_odometer or 0
    avg_price = (total_cost / total_liters) if total_liters > 0 else 0.0

    return {
        "count": count,
        "total_liters": round(total_liters, 2),
        "total_cost": round(total_cost, 2),
        "max_odometer": max_odometer,
        "avg_price_per_liter": round(avg_price, 2)
    }


# --- Сервис и ТО (ServiceLog) ---

async def add_service_log(
    session: AsyncSession,
    user_id: int,
    odometer: int,
    title: str,
    cost: Optional[float] = None,
    notes: Optional[str] = None
) -> ServiceLog:
    """Добавляет запись о ТО или ремонте."""
    log = ServiceLog(
        user_id=user_id,
        odometer=odometer,
        title=title,
        cost=cost,
        notes=notes,
        date=datetime.now()
    )
    session.add(log)
    await session.flush()
    return log


async def get_recent_service_logs(
    session: AsyncSession,
    user_id: int,
    limit: int = 5
) -> List[ServiceLog]:
    """Возвращает последние записи о сервисе пользователя."""
    stmt = (
        select(ServiceLog)
        .where(ServiceLog.user_id == user_id)
        .order_by(desc(ServiceLog.date), desc(ServiceLog.id))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_service_stats(
    session: AsyncSession,
    user_id: int
) -> Dict[str, Any]:
    """Агрегированная статистика по ТО и ремонтам."""
    stmt = select(
        func.count(ServiceLog.id).label("count"),
        func.coalesce(func.sum(ServiceLog.cost), 0.0).label("total_cost")
    ).where(ServiceLog.user_id == user_id)

    result = await session.execute(stmt)
    row = result.one()

    days_stmt = select(
        func.coalesce(func.sum(func.julianday(ServiceLog.date)), 0.0).label("days")
    ).where(ServiceLog.user_id == user_id)
    days_row = (await session.execute(days_stmt)).one()

    return {
        "count": row.count or 0,
        "total_cost": round(float(row.total_cost or 0.0), 2),
        "total_days": round(float(days_row.days or 0.0), 1),
    }


async def get_avg_consumption(
    session: AsyncSession,
    user_id: int,
    window: int = 5
) -> Optional[float]:
    """Средний расход л/100 км по последним заправкам с корректным пробегом."""
    logs = await get_recent_fuel_logs(session, user_id=user_id, limit=window + 1)
    if len(logs) < 2:
        return None

    ordered = sorted(logs, key=lambda x: (x.odometer, x.date))
    total_liters = 0.0
    total_distance = 0
    for prev, cur in zip(ordered, ordered[1:]):
        distance = cur.odometer - prev.odometer
        if 0 < distance <= 3000:  # отсекаем опечатки в одометре
            total_liters += cur.liters
            total_distance += distance

    if total_distance <= 0:
        return None
    return round(total_liters / total_distance * 100, 1)


# --- Поиск и хранение вещей (ItemLocation) ---

async def upsert_item_location(
    session: AsyncSession,
    user_id: int,
    item_name: str,
    location: str
) -> ItemLocation:
    """Сохраняет или обновляет местоположение вещи."""
    clean_name = item_name.strip().lower()
    stmt = select(ItemLocation).where(
        ItemLocation.user_id == user_id,
        func.lower(ItemLocation.item_name) == clean_name
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if item:
        item.item_name = item_name.strip()
        item.location = location.strip()
        item.updated_at = datetime.now()
    else:
        item = ItemLocation(
            user_id=user_id,
            item_name=item_name.strip(),
            location=location.strip(),
            updated_at=datetime.now()
        )
        session.add(item)

    await session.flush()
    return item


_STOPWORDS = {
    "где", "лежит", "находится", "был", "есть", "и", "в", "на", "мне", "мой",
    "моя", "найди", "найти", "поищи", "скажи", "покажи", "что", "какой",
    "какая", "какие", "который", "у", "из", "по", "для", "у меня", "пожалуйста",
    "the", "a", "an", "is", "are", "of", "in", "on", "my", "where", "find",
}

# Окончания, которые стоит срезать для сравнения по префиксу (русские + английские).
_SUFFIXES = (
    "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими", "ый", "ий",
    "ая", "яя", "ое", "ее", "ые", "ие", "ах", "ях", "ов", "ев", "ью", "ия",
    "ка", "ки", "ку", "ов", "ам", "ям", "ом", "ем", "ул", "ешь", "ете", "ал",
    "s", "es", "ed", "ing",
)


def _stem(word: str) -> str:
    """Грубый префиксный стем: 'домкратами' -> 'домкрат', 'дрели' -> 'дрел'."""
    w = word.lower()
    for suf in _SUFFIXES:
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _query_stems(query: str) -> List[str]:
    """Разбивает запрос на значимые основы, отбрасывая служебные слова."""
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", query.lower())
    stems: List[str] = []
    for w in words:
        if len(w) < 3 or w in _STOPWORDS:
            continue
        stem = _stem(w)
        if len(stem) >= 3 and stem not in stems:
            stems.append(stem)
    return stems


def _token_overlap_score(query: str, candidate: str) -> int:
    """
    Оценка совпадения запроса и кандидата: 0 — совпадений нет.
    Учитывает точное равенство, вхождение целиком, совпадение основ слов
    и совпадение по префиксу. Запрос из нескольких значимых слов получает бонус
    только если совпали все — тогда результат предсказуемо лучший.
    """
    q = query.lower().strip()
    c = candidate.lower().strip()
    if not q or not c:
        return 0

    if q == c:
        return 200

    q_stems = _query_stems(q)
    c_stems = _query_stems(c)
    if not q_stems:
        return 0

    score = 0
    matched_all = True

    for qs in q_stems:
        if qs in c_stems:
            score += 20  # слово совпало целиком
        elif any(cs.startswith(qs) or qs.startswith(cs) for cs in c_stems if len(cs) >= 3):
            score += 14  # общая основа / префикс
        elif any(qs in cs for cs in c_stems):
            score += 8  # вхождение в слово («подшипник» -> «подшипников»)
        else:
            matched_all = False

    if matched_all:
        # Все слова нашлись — это сильный сигнал, иначе штрафуем частичное совпадение
        score += 30 + min(len(q_stems), 4) * 5

    # Непрерывное вхождение всей фразы (без стоп- слов) — тоже сильный сигнал
    phrase = " ".join(q_stems)
    if phrase and phrase in c:
        score += 40

    # Короткий запрос, целиком попавший в кандидата
    if len(q) >= 3 and q in c:
        score += 25

    return score


async def search_item_locations(
    session: AsyncSession,
    user_id: int,
    query: str,
    limit: int = 5
) -> List[ItemLocation]:
    """
    Ищет вещи по неполному совпадению названия или места хранения.

    SQL-префильтр LIKE здесь неприменим: LIKE в SQLite работает только с ASCII,
    поэтому запрос «домкрат» никогда не нашёл бы «Домкрат». Инвентарь гаража
    небольшой (десятки записей), поэтому забираем его целиком и ранжируем в Python:
    точное совпадение > вхождение > совпадение по основе слова > совпадение префикса.
    """
    query = (query or "").strip()
    if not query:
        return []

    stmt = (
        select(ItemLocation)
        .where(ItemLocation.user_id == user_id)
        .limit(500)
    )
    result = await session.execute(stmt)
    candidates = list(result.scalars().all())

    scored: List[tuple[int, datetime, ItemLocation]] = []
    for item in candidates:
        name_score = _token_overlap_score(query, item.item_name)
        location_score = _token_overlap_score(query, item.location) - 10  # место менее важно
        best = max(name_score, location_score)
        if best > 0:
            scored.append((best, item.updated_at, item))

    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [item for _, _, item in scored[:limit]]


async def list_all_items(
    session: AsyncSession,
    user_id: int
) -> List[ItemLocation]:
    """Возвращает список всех зарегистрированных вещей пользователя."""
    stmt = (
        select(ItemLocation)
        .where(ItemLocation.user_id == user_id)
        .order_by(ItemLocation.item_name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_item_location(
    session: AsyncSession,
    user_id: int,
    item_name: str
) -> bool:
    """Удаляет вещь из базы данных."""
    stmt = delete(ItemLocation).where(
        ItemLocation.user_id == user_id,
        func.lower(ItemLocation.item_name) == item_name.strip().lower()
    )
    result = await session.execute(stmt)
    return result.rowcount > 0


# --- Задачник и напоминания (Task) ---

async def add_task(
    session: AsyncSession,
    user_id: int,
    title: str,
    due_date: Optional[str] = None,
    due_at: Optional[datetime] = None
) -> Task:
    """Добавляет задачу или напоминание в список дел."""
    task = Task(
        user_id=user_id,
        title=title.strip(),
        due_date=due_date.strip() if due_date else None,
        due_at=due_at,
        is_completed=False,
        created_at=datetime.now()
    )
    session.add(task)
    await session.flush()
    return task


async def get_active_tasks(
    session: AsyncSession,
    user_id: int,
    limit: int = 50
) -> List[Task]:
    """
    Возвращает активные задачи, отсортированные по важности:
    сначала просроченные и те, у которых есть срок (по возрастанию), затем без срока.
    """
    now = datetime.now()
    stmt = (
        select(Task)
        .where(Task.user_id == user_id, Task.is_completed.is_(False))
        .order_by(
            # Задачи со сроком — выше и раньше
            asc(Task.due_at.is_(None)),
            asc(Task.due_at),
            desc(Task.created_at),
        )
        .limit(limit)
    )
    result = await session.execute(stmt)
    tasks = list(result.scalars().all())

    # Просроченные (из-за часового пояса/ручного ввода) прижимаем к началу списка
    overdue = [t for t in tasks if t.due_at and t.due_at < now]
    upcoming = [t for t in tasks if t.due_at and t.due_at >= now]
    undated = [t for t in tasks if not t.due_at]
    return overdue + upcoming + undated


async def get_task(
    session: AsyncSession,
    user_id: int,
    task_id: int
) -> Optional[Task]:
    """Возвращает задачу по id (с проверкой владельца)."""
    stmt = select(Task).where(Task.user_id == user_id, Task.id == task_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def complete_task(
    session: AsyncSession,
    user_id: int,
    task_id: int
) -> bool:
    """Отмечает задачу как выполненную."""
    stmt = select(Task).where(Task.user_id == user_id, Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if task:
        task.is_completed = True
        task.completed_at = datetime.now()
        await session.flush()
        return True
    return False


async def uncomplete_task(
    session: AsyncSession,
    user_id: int,
    task_id: int
) -> bool:
    """Возвращает задачу в активные (отмена выполнения)."""
    stmt = select(Task).where(Task.user_id == user_id, Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if task and task.is_completed:
        task.is_completed = False
        task.completed_at = None
        await session.flush()
        return True
    return False


async def complete_all_tasks(
    session: AsyncSession,
    user_id: int
) -> int:
    """Закрывает все активные задачи разом. Возвращает количество закрытых."""
    now = datetime.now()
    stmt = (
        update(Task)
        .where(Task.user_id == user_id, Task.is_completed.is_(False))
        .values(is_completed=True, completed_at=now)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount or 0


async def delete_task(
    session: AsyncSession,
    user_id: int,
    task_id: int
) -> bool:
    """Удаляет задачу насовсем (с проверкой владельца)."""
    stmt = delete(Task).where(Task.user_id == user_id, Task.id == task_id)
    result = await session.execute(stmt)
    await session.flush()
    return bool(result.rowcount)


async def get_recent_completed_tasks(
    session: AsyncSession,
    user_id: int,
    limit: int = 5
) -> List[Task]:
    """Недавно закрытые задачи — чтобы предложить кнопку «вернуть»."""
    stmt = (
        select(Task)
        .where(Task.user_id == user_id, Task.is_completed.is_(True))
        .order_by(desc(Task.completed_at), desc(Task.id))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# --- История диалога (ChatHistory / Память контекста) ---

async def add_chat_message(
    session: AsyncSession,
    user_id: int,
    role: str,
    content: str
) -> ChatHistory:
    """Сохраняет реплику диалога (пользователя или ассистента) в базу данных."""
    msg = ChatHistory(
        user_id=user_id,
        role=role,
        content=content,
        created_at=datetime.now()
    )
    session.add(msg)
    await session.flush()
    return msg


async def get_recent_chat_history(
    session: AsyncSession,
    user_id: int,
    limit: int = 10
) -> List[Dict[str, str]]:
    """
    Возвращает последние N сообщений диалога пользователя в хронологическом порядке (от старых к новым).
    Формат: [{'role': 'user'|'assistant', 'content': '...'}]
    """
    stmt = (
        select(ChatHistory)
        .where(ChatHistory.user_id == user_id)
        .order_by(desc(ChatHistory.created_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    records = list(result.scalars().all())
    # Разворачиваем, чтобы диалог шел в хронологическом порядке
    records.reverse()
    return [{"role": r.role, "content": r.content} for r in records]


async def clear_chat_history(
    session: AsyncSession,
    user_id: int
) -> int:
    """Очищает историю диалога пользователя (сброс контекста памяти)."""
    stmt = delete(ChatHistory).where(ChatHistory.user_id == user_id)
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount


async def prune_chat_history(
    session: AsyncSession,
    user_id: int,
    keep_last: int = 200,
    max_age_days: int = 30
) -> int:
    """
    Подрезает историю диалога, чтобы таблица не росла бесконечно.
    Оставляем последние keep_last сообщений и всё, что моложе max_age_days.
    """
    cutoff = datetime.now() - timedelta(days=max_age_days)

    stale = delete(ChatHistory).where(
        ChatHistory.user_id == user_id,
        ChatHistory.created_at < cutoff,
    )
    await session.execute(stale)

    id_stmt = (
        select(ChatHistory.id)
        .where(ChatHistory.user_id == user_id)
        .order_by(desc(ChatHistory.created_at), desc(ChatHistory.id))
        .offset(keep_last)
    )
    old_ids = list((await session.execute(id_stmt)).scalars().all())
    if old_ids:
        await session.execute(delete(ChatHistory).where(ChatHistory.id.in_(old_ids)))

    await session.flush()
    return len(old_ids)


