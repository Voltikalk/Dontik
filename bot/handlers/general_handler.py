import logging
from aiogram import Router, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from bot.database.db import get_session
from bot.database import crud
from bot.keyboards.inline import get_tasks_keyboard

logger = logging.getLogger(__name__)

router = Router(name="general_handler_router")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    Приветствие по имени и подсказка по использованию голосового ввода.
    """
    first_name = message.from_user.first_name or "Автомобилист"
    safe_name = html.quote(first_name)

    text = (
        f"👋 <b>Привет, {safe_name}!</b>\n\n"
        "Я твой личный ассистент по автомобилю, гаражу и <b>задачник</b>.\n\n"
        "🎙 <b>Просто зажми микрофон и скажи что угодно своими словами:</b>\n"
        "• <i>«Заправил 35 литров на две тысячи, пробег 150 000»</i>\n"
        "• <i>«Поменял масло и фильтры, пробег 152 000»</i>\n"
        "• <i>«Положил домкрат под верстак»</i> или <i>«Где лежит домкрат?»</i>\n"
        "• <i>«Запиши на завтра съездить на дачу, купить грабли»</i>\n"
        "• <i>«Какие у меня дела на завтра?»</i>\n\n"
        "📊 <b>Команды:</b>\n"
        "/stats — сводка по заправкам и ТО\n"
        "/tasks — список актуальных задач и напоминаний"
    )
    await message.answer(text)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """
    Обработчик команды /stats.
    Выводит сводку по последней заправке и последнему ремонту.
    """
    user_id = message.from_user.id

    async with get_session() as session:
        last_fuel = await crud.get_last_fuel_log(session, user_id=user_id)
        last_service = await crud.get_last_service_log(session, user_id=user_id)

    lines = ["📊 <b>Сводка по автомобилю:</b>\n"]

    # Блок последней заправки
    if last_fuel:
        fuel_date = last_fuel.date.strftime("%d.%m.%Y")
        station_str = f" (АЗС: {html.quote(last_fuel.station_name)})" if last_fuel.station_name else ""
        lines.append(
            f"⛽ <b>Последняя заправка ({fuel_date}):</b>\n"
            f"• Объем: <code>{last_fuel.liters:.1f} л</code>\n"
            f"• Стоимость: <code>{last_fuel.cost:,.0f} ₽</code>\n"
            f"• Пробег: <code>{last_fuel.odometer:,} км</code>{station_str}\n".replace(",", " ")
        )
    else:
        lines.append("⛽ <b>Последняя заправка:</b> <i>записей пока нет</i>\n")

    # Блок последнего сервиса / ТО
    if last_service:
        service_date = last_service.date.strftime("%d.%m.%Y")
        cost_str = f" на <code>{last_service.cost:,.0f} ₽</code>" if last_service.cost else ""
        notes_str = f"\n• Заметки: <i>{html.quote(last_service.notes)}</i>" if last_service.notes else ""
        lines.append(
            f"🔧 <b>Последнее ТО / ремонт ({service_date}):</b>\n"
            f"• Работы: <b>{html.quote(last_service.title)}</b>{cost_str}\n"
            f"• Пробег: <code>{last_service.odometer:,} км</code>{notes_str}\n".replace(",", " ")
        )
    else:
        lines.append("🔧 <b>Последнее ТО / ремонт:</b> <i>записей пока нет</i>\n")

    await message.answer("\n".join(lines))


@router.message(Command("tasks", "todo"))
async def cmd_tasks(message: Message):
    """
    Обработчик команды /tasks и /todo.
    Выводит список активных задач пользователя.
    """
    user_id = message.from_user.id

    async with get_session() as session:
        tasks = await crud.get_active_tasks(session, user_id=user_id)

    if not tasks:
        await message.answer(
            "🎉 <b>Список задач пуст!</b>\n\n"
            "Чтобы добавить дело или покупку, просто скажите голосовым сообщением, например:\n"
            "<i>«Запиши на завтра съездить на дачу, купить грабли»</i>"
        )
        return

    lines = ["📋 <b>Твой актуальный список дел и задач:</b>\n"]
    for idx, t in enumerate(tasks, 1):
        due_str = f" <i>(срок: {html.quote(t.due_date)})</i>" if t.due_date else ""
        lines.append(f"{idx}. <b>{html.quote(t.title)}</b>{due_str}")

    kb = get_tasks_keyboard(tasks)
    await message.answer("\n".join(lines), reply_markup=kb)

