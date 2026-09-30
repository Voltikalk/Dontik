"""Команды бота, быстрые фразы и обработка обычного текста."""

import logging

from aiogram import F, Router, html
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.database import crud
from bot.database.db import get_session
from bot.emojis import (
    E_ALERT,
    E_BULB,
    E_CHART,
    E_DROP,
    E_GLOBE,
    E_HELLO,
    E_MIC,
    E_NOTE,
    E_PIN,
    E_QUESTION,
    E_REPEAT,
    E_WRENCH,
)
from bot.handlers.input_handler import process_input, send_tasks_list
from bot.keyboards.inline import get_main_menu_keyboard
from bot.services.agents import MultiAgentOrchestrator
from bot.services.formatters import (
    fmt_int,
    fmt_km,
    fmt_money,
    format_all_items_list,
)

logger = logging.getLogger(__name__)

router = Router(name="general_router")

orchestrator = MultiAgentOrchestrator()

# Естественные синонимы команд: фраза пользователя -> команда.
# Один фразе несколько синонимов, группируем в кортежи.
NATURAL_COMMAND_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("start", ("меню", "старт", "начать", "панель", "главное")),
    ("tasks", (
        "задачи", "дела", "список задач", "список дел", "что сделать",
        "планы", "todo", "todo list", "задача", "чем заняться",
    )),
    ("stats", (
        "статистика", "статы", "расходы", "заправки", "сводка",
        "итоги", "статистика по машине",
    )),
    ("items", ("вещи", "гараж", "инвентарь", "где что лежит", "склад", "дача")),
    ("history_fuel", ("история заправок", "журнал заправок", "мои заправки")),
    ("history_service", ("история сервиса", "журнал то", "мои ремонты")),
    ("mail", (
        "почта", "письма", "входящие", "входящие письма", "новые письма",
        "проверь почту", "проверить почту", "что на почте",
    )),
    ("help", ("помощь", "справка", "инструкция", "как пользоваться", "что ты умеешь")),
    ("clear", (
        "забудь", "сброс", "сбрось контекст", "очисти контекст",
        "очистить контекст", "очисти память", "очистить память",
        "начнем заново", "начать заново", "забудь все",
    )),
)

NATURAL_COMMANDS: dict[str, str] = {}
for _command, _phrases in NATURAL_COMMAND_GROUPS:
    for _phrase in _phrases:
        NATURAL_COMMANDS[_phrase] = _command


def _match_natural_command(text: str) -> str | None:
    """Возвращает команду, если фраза целиком совпала с синонимом.

    Совпадение должно быть полным: «купить грабли» — это задача, а не команда.
    """
    normalized = " ".join((text or "").lower().strip().rstrip("!?.»").split())
    if not normalized:
        return None
    return NATURAL_COMMANDS.get(normalized)


# --- /start ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Приветствие с понятным описанием возможностей."""
    await state.clear()
    first_name = html.quote(message.from_user.first_name or "водитель")

    text = (
        f"{E_HELLO} <b>Привет, {first_name}!</b>\n\n"
        f"Я <b>Пётр</b> — твой ежедневный помощник и авто-гаражный ассистент. "
        f"Пиши текстом или просто говори голосом.\n\n"
        f"{E_NOTE} <b>Задачи и покупки</b>\n"
        f"  <i>«Запиши на завтра съездить на дачу и купить грабли»</i>\n"
        f"{E_DROP} <b>Заправки</b>\n"
        f"  <i>«Заправил 42 литра на 2500, пробег 154300, Лукойл»</i>\n"
        f"{E_WRENCH} <b>Сервис и ремонты</b>\n"
        f"  <i>«Поменял масло и фильтр, 6200 руб, пробег 155000»</i>\n"
        f"{E_PIN} <b>Вещи в гараже</b>\n"
        f"  <i>«Положил домкрат под верстак»</i> / <i>«Где лежит домкрат?»</i>\n"
        f"{E_GLOBE} <b>Вопросы, советы и поиск</b>\n"
        f"  <i>«Курс доллара»</i> · <i>«Как прокачать тормоза на Ниве?»</i>\n"
        f"{E_CHART} <b>Математика и расчёты</b>\n"
        f"  <i>«Реши уравнение x² + 5x − 6 = 0»</i> — формулы рисуются прямо в чате\n"
        f"{E_BULB} <b>Файлы и фото</b>\n"
        f"  PDF, Word, Excel, CSV, фото чеков, деталей и схем — разберу и отвечу\n\n"
        f"{E_MIC} <b>Команды:</b> /tasks · /stats · /items · /agent · /clear · /help"
    )
    await message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)


# --- /tasks ---

@router.message(Command("tasks", "todo"))
async def cmd_tasks(message: Message):
    await send_tasks_list(message, message.from_user.id)


# --- /stats ---

@router.message(Command("stats", "statistics"))
async def cmd_stats(message: Message):
    """Сводка: последняя заправка, последний сервис, средний расход."""
    user_id = message.from_user.id

    async with get_session() as session:
        last_fuel = await crud.get_last_fuel_log(session, user_id=user_id)
        last_service = await crud.get_last_service_log(session, user_id=user_id)
        consumption = await crud.get_avg_consumption(session, user_id=user_id)

    lines = [f"{E_CHART} <b>Сводка по автомобилю</b>\n"]

    if last_fuel:
        price = (last_fuel.cost / last_fuel.liters) if last_fuel.liters else None
        price_str = f" · {fmt_money(price, 2)}/л" if price else ""
        station = f" · {html.quote(last_fuel.station_name)}" if last_fuel.station_name else ""
        lines.append(
            f"{E_DROP} <b>Последняя заправка</b> ({last_fuel.date.strftime('%d.%m.%Y')})\n"
            f"  <code>{last_fuel.liters:.1f} л</code> на <code>{fmt_money(last_fuel.cost)}</code>{price_str}\n"
            f"  пробег <code>{fmt_km(last_fuel.odometer)}</code>{station}"
        )
    else:
        lines.append(f"{E_DROP} <b>Заправок пока нет</b> — <i>скажи «заправился»</i>")

    if last_service:
        cost = f" на <code>{fmt_money(last_service.cost)}</code>" if last_service.cost else ""
        lines.append(
            f"{E_WRENCH} <b>Последний сервис</b> ({last_service.date.strftime('%d.%m.%Y')})\n"
            f"  {html.quote(last_service.title)}{cost}\n"
            f"  пробег <code>{fmt_km(last_service.odometer)}</code>"
        )
    else:
        lines.append(f"{E_WRENCH} <b>Записей сервиса нет</b> — <i>скажи, что делал</i>")

    if consumption:
        lines.append(f"\n{E_DROP} Средний расход: <code>{consumption} л / 100 км</code>")

    await message.answer(
        "\n\n".join(lines),
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )


# --- /items ---

@router.message(Command("items", "garage"))
async def cmd_items(message: Message):
    user_id = message.from_user.id
    async with get_session() as session:
        items = await crud.list_all_items(session, user_id=user_id)

    text = format_all_items_list(items)
    if items:
        text += f"\n\nВсего предметов: <code>{fmt_int(len(items))}</code>"
    await message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)


# --- /agent ---

AGENT_HELP = (
    f"{E_BULB} <b>Команда субагентов</b>\n\n"
    f"Запускает several специалистов параллельно и собирает один проверенный отчёт:\n"
    f"• <b>Поиск</b> — цены, артикулы, актуальные предложения\n"
    f"• <b>Техэксперт</b> — регламент, инструмент, нюансы ремонта\n"
    f"• <b>Смета</b> — расчёт бюджета и сравнение вариантов\n"
    f"• <b>Планировщик</b> — пошаговый чек-лист\n"
    f"• <b>Критик</b> — ищет ошибки и скрытые расходы\n\n"
    f"<b>Примеры:</b>\n"
    f"<code>/agent Замена сцепления ВАЗ 2121: регламент, цены на комплект Valeo, план работ</code>\n"
    f"<code>/agent Капитальный ремонт беседки: смета материалов и этапы</code>\n"
    f"<code>/agent Почему двигатель перегревает на Ниве?</code>"
)


@router.message(Command("agent", "research"))
async def cmd_agent(message: Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await message.answer(AGENT_HELP, parse_mode=ParseMode.HTML)
        return

    task = parts[1].strip()
    status_msg = await message.answer(f"{E_BULB} <i>Запускаю субагентов...</i>")
    last_rendered = ""

    async def update_progress(msg: str) -> None:
        """Редактирует статус, но не чаще раза в секунду и только при реальном изменении."""
        nonlocal last_rendered
        if msg == last_rendered:
            return
        try:
            await status_msg.edit_text(msg)
            last_rendered = msg
        except Exception:  # noqa: BLE001
            pass

    try:
        history = await _load_history(user_id)
        report = await orchestrator.execute_task(
            task=task,
            context={"history": history} if history else {},
            on_progress=update_progress,
        )

        from bot.services.formatters import send_formatted_message

        try:
            await status_msg.delete()
        except Exception:  # noqa: BLE001
            pass
        await send_formatted_message(message, report)

        async with get_session() as session:
            await crud.add_chat_message(session, user_id=user_id, role="user", content=f"/agent {task}")
            await crud.add_chat_message(session, user_id=user_id, role="assistant", content=report[:4000])

    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка субагентов: %s", exc, exc_info=True)
        try:
            await status_msg.delete()
        except Exception:  # noqa: BLE001
            pass
        await message.answer(
            f"{E_ALERT} <b>Команда субагентов не справилась.</b>\n"
            f"Попробуй уточнить задачу или задать вопрос обычным сообщением.",
            parse_mode=ParseMode.HTML,
        )


async def _load_history(user_id: int) -> list[dict]:
    try:
        async with get_session() as session:
            return await crud.get_recent_chat_history(session, user_id=user_id, limit=6)
    except Exception:  # noqa: BLE001
        return []


# --- /clear ---

@router.message(Command("clear", "reset"))
async def cmd_clear(message: Message):
    user_id = message.from_user.id
    async with get_session() as session:
        removed = await crud.clear_chat_history(session, user_id=user_id)

    await message.answer(
        f"{E_REPEAT} <b>Память диалога очищена</b> (удалено сообщений: {fmt_int(removed)}).\n"
        f"Начинаем с чистого листа — задавай новый вопрос.",
        parse_mode=ParseMode.HTML,
    )


# --- /help ---

@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        f"{E_BULB} <b>Как пользоваться</b>\n\n"
        f"Можешь писать текстом или голосом — работает одинаково.\n\n"
        f"<b>Задачи и покупки</b>\n"
        f"• <i>«Запиши на завтра купить масло и фильтр»</i>\n"
        f"• <i>«Напомни в субботу поменять резину»</i>\n"
        f"• <i>«Какие у меня дела?»</i> · <i>«Удали задачу про грабли»</i>\n\n"
        f"<b>Машина и гараж</b>\n"
        f"• <i>«Заправил 40 литров на 2400, пробег 152000, Газпром»</i>\n"
        f"• <i>«Поменял колодки, 8000 руб, пробег 156000»</i>\n"
        f"• <i>«Положил ключ на 13 в синий ящик»</i>\n"
        f"• <i>«Где лежит домкрат?»</i>\n\n"
        f"<b>Вопросы, советы, поиск</b>\n"
        f"• <i>«Какая погода в Самаре?»</i> · <i>«Курс доллара»</i>\n"
        f"• <i>«Какой штраф за превышение на 20 км/ч?»</i>\n"
        f"• <i>«Посчитай расход топлива по 10 заправкам»</i>\n\n"
        f"<b>Математика</b>\n"
        f"• <i>«Реши уравнение x² + 5x − 6 = 0»</i>\n"
        f"• <i>«Найди производную функции»</i> · <i>«Вычисли интеграл»</i>\n"
        f"• <i>«Посчитай скидку 15% от 3400»</i>\n"
        f"Формулы выводятся нативными блоками прямо в чате.\n\n"
        f"<b>Файлы и фото</b>\n"
        f"Пришли PDF, Word, Excel, CSV или фото — разберу содержимое и отвечу. "
        f"В подписи можно сразу написать вопрос.\n\n"
        f"{E_PIN} <b>Команды</b>\n"
        f"/tasks — задачи · /stats — сводка · /items — вещи\n"
        f"/agent — субагенты · /mail — почта · /clear — сброс памяти\n"
        f"/start — главное меню · /help — эта справка"
    )
    await message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)


# --- Обычный текст и естественные команды ---

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, state: FSMContext):
    raw_text = (message.text or "").strip()
    if not raw_text:
        return

    command = _match_natural_command(raw_text)

    if command == "start":
        await cmd_start(message, state)
    elif command == "tasks":
        await send_tasks_list(message, message.from_user.id)
    elif command == "stats":
        await cmd_stats(message)
    elif command == "items":
        await cmd_items(message)
    elif command in ("history_fuel", "history_service"):
        await _send_history(message, message.from_user.id, command)
    elif command == "mail":
        from bot.handlers.email_handler import cmd_check_mail

        await cmd_check_mail(message)
    elif command == "help":
        await cmd_help(message)
    elif command == "clear":
        await cmd_clear(message)
    else:
        await process_input(message, message.bot, state, raw_text, is_voice=False)


async def _send_history(message: Message, user_id: int, which: str) -> None:
    """Показывает историю заправок или сервиса."""
    from bot.services.formatters import format_fuel_history, format_service_history

    async with get_session() as session:
        if which == "history_fuel":
            logs = await crud.get_recent_fuel_logs(session, user_id=user_id, limit=10)
            text = format_fuel_history(logs)
        else:
            logs = await crud.get_recent_service_logs(session, user_id=user_id, limit=10)
            text = format_service_history(logs)

    await message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)


# --- Неизвестная команда ---

@router.message(F.text.startswith("/"))
async def handle_unknown_command(message: Message):
    """Не молчим на опечатки, а подсказываем похожие команды."""
    raw = (message.text or "").split()[0].lstrip("/").split("@")[0].lower()
    suggestions = []

    known = [
        "start", "help", "tasks", "todo", "stats", "statistics",
        "items", "garage", "agent", "research", "clear", "reset", "mail",
    ]
    close = [k for k in known if k.startswith(raw) or raw in k]
    if close:
        suggestions = close[:3]
    else:
        suggestions = ["start", "help", "tasks"]

    hint = ", ".join(f"<code>/{s}</code>" for s in suggestions)
    await message.answer(
        f"{E_QUESTION} Не знаю команды <code>/{html.quote(raw)}</code>.\n\n"
        f"Возможно, имелось в виду: {hint}\n"
        f"Полный список — <code>/help</code>",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )


# --- Всё остальное: стикеры, видео, контакты и прочее ---

@router.message()
async def handle_anything_else(message: Message):
    """Ловим всё, что бот не умеет, чтобы пользователь не думал, что он завис."""
    chat_action = message.content_type or "этот тип"

    await message.answer(
        f"{E_QUESTION} Пока не понимаю, что с этим делать (<code>{html.quote(chat_action)}</code>).\n\n"
        f"{E_MIC} Лучше всего работает <b>голос или текст</b>:\n"
        f"• <i>«Заправил 40 литров на 2400»</i>\n"
        f"• <i>«Запиши купить масло»</i>\n"
        f"• <i>«Реши уравнение x² = 16»</i>\n\n"
        f"Файлы PDF / Word / Excel и фотографии тоже понимаю — просто пришли их.\n"
        f"Команды: <code>/help</code>",
        parse_mode=ParseMode.HTML,
    )