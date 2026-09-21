from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User, FuelLog, ServiceLog, ItemLocation


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
            is_admin=is_admin
        )
        session.add(user)
        await session.flush()
    else:
        # Обновляем имя, если изменилось
        if user.full_name != full_name:
            user.full_name = full_name
            await session.flush()

    return user


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
        .order_by(desc(ServiceLog.date))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


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


async def search_item_locations(
    session: AsyncSession,
    user_id: int,
    query: str
) -> List[ItemLocation]:
    """Ищет вещи по неполному совпадению названия."""
    pattern = f"%{query.strip().lower()}%"
    stmt = (
        select(ItemLocation)
        .where(
            ItemLocation.user_id == user_id,
            func.lower(ItemLocation.item_name).like(pattern)
        )
        .order_by(ItemLocation.item_name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


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
