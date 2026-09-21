import logging
from aiogram import Router, html
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import ConfirmCallback, ActionCallback, get_main_menu_keyboard
from bot.services.draft_store import pop_draft
from bot.database.db import get_session
from bot.database import crud
from bot.services.formatters import (
    format_fuel_history,
    format_service_history,
    format_all_items_list,
    format_stats_summary
)

logger = logging.getLogger(__name__)

router = Router(name="callbacks_router")


@router.callback_query(ConfirmCallback.filter())
async def handle_confirm_callback(callback: CallbackQuery, callback_data: ConfirmCallback):
    """
    Обработка подтверждения сохранения записи в БД.
    """
    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer("Сообщение недоступно.", show_alert=True)
        return

    draft_id = callback_data.draft_id
    action_type = callback_data.action
    user_id = callback.from_user.id

    draft = pop_draft(draft_id)
    if not draft:
        await callback.answer("⏳ Срок действия этой карточки истек или она уже сохранена.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    data = draft.get("data", {})

    async with get_session() as session:
        if action_type == "fuel":
            liters = float(data.get("liters") or 0.0)
            cost = float(data.get("cost") or 0.0)
            odometer = int(data.get("odometer") or 0)
            station_name = data.get("station") or data.get("station_name")

            log = await crud.add_fuel_log(
                session=session,
                user_id=user_id,
                liters=liters,
                cost=cost,
                odometer=odometer,
                station_name=station_name
            )

            odometer_str = f"{odometer:,} км".replace(",", " ")
            station_str = f" (АЗС: {html.quote(station_name)})" if station_name else ""

            text = (
                "✅ <b>Заправка успешно занесена в журнал!</b>\n\n"
                f"• <b>Объем:</b> <code>{liters:.1f} л</code>\n"
                f"• <b>Сумма:</b> <code>{cost:,.2f} ₽</code>\n"
                f"• <b>Пробег:</b> <code>{odometer_str}</code>{station_str}\n"
                f"• <b>Номер записи:</b> #<code>{log.id}</code>"
            )
            await callback.message.edit_text(text, reply_markup=None)
            await callback.answer("✅ Заправка сохранена!")

        elif action_type == "service":
            odometer = int(data.get("odometer", 0))
            title = data.get("title", "Техническое обслуживание")
            cost = float(data["cost"]) if data.get("cost") is not None else None
            notes = data.get("notes")

            log = await crud.add_service_log(
                session=session,
                user_id=user_id,
                odometer=odometer,
                title=title,
                cost=cost,
                notes=notes
            )

            odometer_str = f"{odometer:,} км".replace(",", " ")
            cost_str = f"\n• <b>Стоимость:</b> <code>{cost:,.2f} ₽</code>" if cost is not None else ""

            text = (
                "✅ <b>Запись ТО / ремонта сохранена!</b>\n\n"
                f"• <b>Работы:</b> <b>{html.quote(title)}</b>\n"
                f"• <b>Пробег:</b> <code>{odometer_str}</code>{cost_str}\n"
                f"• <b>Номер записи:</b> #<code>{log.id}</code>"
            )
            await callback.message.edit_text(text, reply_markup=None)
            await callback.answer("✅ Запись ТО сохранена!")

        elif action_type == "item":
            item_name = data.get("item_name", "Вещь")
            location = data.get("location", "Гараж")

            item = await crud.upsert_item_location(
                session=session,
                user_id=user_id,
                item_name=item_name,
                location=location
            )

            text = (
                "✅ <b>Местоположение вещи запомнено!</b>\n\n"
                f"• <b>Предмет:</b> <b>{html.quote(item.item_name)}</b>\n"
                f"• <b>Где лежит:</b> <code>{html.quote(item.location)}</code>\n\n"
                "💡 Чтобы найти её в будущем, просто спросите в чате: <i>«Где лежит ...?»</i>"
            )
            await callback.message.edit_text(text, reply_markup=None)
            await callback.answer("✅ Вещь сохранена!")


@router.callback_query(ActionCallback.filter())
async def handle_action_callback(callback: CallbackQuery, callback_data: ActionCallback):
    """
    Обработка кнопок меню и отмены.
    """
    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    action = callback_data.action
    user_id = callback.from_user.id

    if action.startswith("cancel_"):
        draft_id = action.replace("cancel_", "")
        pop_draft(draft_id)
        await callback.message.edit_text("❌ <b>Действие отменено.</b> Запись не была сохранена.", reply_markup=None)
        await callback.answer("Отменено")
        return

    async with get_session() as session:
        if action == "history_fuel":
            logs = await crud.get_recent_fuel_logs(session, user_id=user_id, limit=7)
            text = format_fuel_history(logs)
            await callback.message.answer(text, reply_markup=get_main_menu_keyboard())
            await callback.answer()

        elif action == "history_service":
            logs = await crud.get_recent_service_logs(session, user_id=user_id, limit=7)
            text = format_service_history(logs)
            await callback.message.answer(text, reply_markup=get_main_menu_keyboard())
            await callback.answer()

        elif action == "list_items":
            items = await crud.list_all_items(session, user_id=user_id)
            text = format_all_items_list(items)
            await callback.message.answer(text, reply_markup=get_main_menu_keyboard())
            await callback.answer()

        elif action == "summary_stats":
            fuel_stats = await crud.get_fuel_stats(session, user_id=user_id)
            text = format_stats_summary(fuel_stats)
            await callback.message.answer(text, reply_markup=get_main_menu_keyboard())
            await callback.answer()
