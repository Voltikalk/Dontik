from aiogram import html
from typing import Dict, Any, List
from bot.database.models import FuelLog, ServiceLog, ItemLocation


def format_fuel_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку подтверждения заправки с expandable blockquote."""
    liters = data.get("liters", 0.0)
    cost = data.get("cost", 0.0)
    odometer = data.get("odometer", 0)
    station = data.get("station_name") or "Не указана"

    price_per_l = round(cost / liters, 2) if liters and cost else 0.0

    lines = [
        "⛽ <b>Распознана заправка автомобиля</b>\n",
        f"• <b>Литры:</b> <code>{liters:.1f} л</code>",
        f"• <b>Стоимость:</b> <code>{cost:,.2f} ₽</code>",
        f"• <b>Цена за литр:</b> <code>{price_per_l:.2f} ₽</code>",
        f"• <b>Пробег на одометре:</b> <code>{odometer:,} км</code>".replace(",", " "),
        f"• <b>АЗС:</b> <i>{html.quote(str(station))}</i>\n"
    ]

    if raw_text:
        lines.append(f"<blockquote expandable>🗣 <b>Исходный текст:</b>\n{html.quote(raw_text)}</blockquote>\n")

    lines.append("<i>Подтвердите сохранение записи в журнал:</i>")
    return "\n".join(lines)


def format_service_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку подтверждения ТО / ремонта."""
    title = data.get("title", "Техническое обслуживание")
    cost = data.get("cost")
    odometer = data.get("odometer", 0)
    notes = data.get("notes")

    lines = [
        "🔧 <b>Распознано сервисное обслуживание / ремонт</b>\n",
        f"• <b>Работа / Деталь:</b> <b>{html.quote(str(title))}</b>",
        f"• <b>Пробег:</b> <code>{odometer:,} км</code>".replace(",", " "),
    ]

    if cost is not None:
        lines.append(f"• <b>Стоимость:</b> <code>{cost:,.2f} ₽</code>")
    if notes:
        lines.append(f"• <b>Заметки:</b> <i>{html.quote(str(notes))}</i>")

    lines.append("")
    if raw_text:
        lines.append(f"<blockquote expandable>🗣 <b>Исходный текст:</b>\n{html.quote(raw_text)}</blockquote>\n")

    lines.append("<i>Подтвердите сохранение записи в журнал:</i>")
    return "\n".join(lines)


def format_location_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку сохранения местоположения вещи."""
    item_name = data.get("item_name", "Вещь")
    location = data.get("location", "Гараж")

    lines = [
        "📦 <b>Запись в инвентарь гаража/дачи</b>\n",
        f"• <b>Предмет:</b> <b>{html.quote(str(item_name))}</b>",
        f"• <b>Место хранения:</b> <code>{html.quote(str(location))}</code>\n"
    ]

    if raw_text:
        lines.append(f"<blockquote expandable>🗣 <b>Исходный текст:</b>\n{html.quote(raw_text)}</blockquote>\n")

    lines.append("<i>Запомнить это место?</i>")
    return "\n".join(lines)


def format_found_items(items: List[ItemLocation], query: str) -> str:
    """Форматирует результаты поиска вещей в гараже."""
    if not items:
        return (
            f"🔍 По запросу «<b>{html.quote(query)}</b>» ничего не найдено.\n\n"
            "💡 Чтобы бот запомнил вещь, просто скажите или напишите, например:\n"
            "<i>«Положил домкрат в левый угол у ворот»</i>"
        )

    lines = [f"📍 <b>Найдено в гараже / на даче (запрос: {html.quote(query)}):</b>\n"]
    for idx, it in enumerate(items, 1):
        updated = it.updated_at.strftime("%d.%m.%Y")
        lines.append(
            f"{idx}. <b>{html.quote(it.item_name)}</b>\n"
            f"   ↳ 📍 <code>{html.quote(it.location)}</code> <i>(обновлено: {updated})</i>"
        )
    return "\n".join(lines)


def format_all_items_list(items: List[ItemLocation]) -> str:
    """Форматирует полный список вещей пользователя."""
    if not items:
        return "📦 В гараже пока ничего не записано. Скажите или напишите, что и куда вы положили!"

    lines = ["📦 <b>Список вещей на хранении:</b>\n"]
    for idx, it in enumerate(items, 1):
        lines.append(f"{idx}. <b>{html.quote(it.item_name)}</b> — <code>{html.quote(it.location)}</code>")
    lines.append("\n💡 <i>Чтобы найти конкретную вещь, спросите «Где лежит ...?»</i>")
    return "\n".join(lines)


def format_fuel_history(logs: List[FuelLog]) -> str:
    """Форматирует историю заправок."""
    if not logs:
        return "⛽ История заправок пока пуста."

    lines = ["⛽ <b>Последние заправки:</b>\n"]
    for it in logs:
        date_str = it.date.strftime("%d.%m.%Y")
        station_str = f" ({html.quote(it.station_name)})" if it.station_name else ""
        lines.append(
            f"• <b>{date_str}</b>{station_str}: "
            f"<code>{it.liters:.1f} л</code> на <code>{it.cost:,.0f} ₽</code> | "
            f"<code>{it.odometer:,} км</code>".replace(",", " ")
        )
    return "\n".join(lines)


def format_service_history(logs: List[ServiceLog]) -> str:
    """Форматирует историю ТО."""
    if not logs:
        return "🔧 История обслуживания и ремонтов пока пуста."

    lines = ["🔧 <b>Последние записи ТО и сервиса:</b>\n"]
    for it in logs:
        date_str = it.date.strftime("%d.%m.%Y")
        cost_str = f" — <code>{it.cost:,.0f} ₽</code>" if it.cost else ""
        lines.append(
            f"• <b>{date_str}</b> | <code>{it.odometer:,} км</code>: "
            f"<b>{html.quote(it.title)}</b>{cost_str}".replace(",", " ")
        )
    return "\n".join(lines)


def format_stats_summary(fuel_stats: Dict[str, Any]) -> str:
    """Форматирует общую статистику расходов."""
    lines = [
        "📊 <b>Сводная статистика по автомобилю:</b>\n",
        f"• <b>Всего заправок:</b> <code>{fuel_stats.get('count', 0)}</code>",
        f"• <b>Суммарный объем топлива:</b> <code>{fuel_stats.get('total_liters', 0.0)} л</code>",
        f"• <b>Всего потрачено на топливо:</b> <code>{fuel_stats.get('total_cost', 0.0):,.2f} ₽</code>",
        f"• <b>Средняя цена за литр:</b> <code>{fuel_stats.get('avg_price_per_liter', 0.0):.2f} ₽</code>",
        f"• <b>Текущий зафиксированный пробег:</b> <code>{fuel_stats.get('max_odometer', 0):,} км</code>".replace(",", " ")
    ]
    return "\n".join(lines)
