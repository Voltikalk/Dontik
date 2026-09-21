import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.database.db import get_session
from bot.database import crud

logger = logging.getLogger(__name__)

router = Router(name="callback_handler_router")


@router.callback_query(F.data == "confirm_entry")
async def process_confirm_entry(callback: CallbackQuery, state: FSMContext):
    """
    Подтверждение и сохранение записи в SQLite.
    1. Достает данные из FSM.
    2. Записывает соответствующий объект в БД (FuelLog / ServiceLog / ItemLocation).
    3. Рассчитывает средний расход топлива при наличии предыдущей заправки.
    4. Очищает состояние FSM и обновляет сообщение.
    """
    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    state_data = await state.get_data()
    intent = state_data.get("intent")
    data = state_data.get("data", {})
    user_id = callback.from_user.id

    if not intent or not data:
        await callback.answer("Срок действия карточки истек или данные уже сохранены.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await state.clear()
        return

    result_text = "✅ Записано в базу!"

    async with get_session() as session:
        if intent == "fuel":
            liters = float(data.get("liters") or 0.0)
            cost = float(data.get("cost") or 0.0)
            odometer = int(data.get("odometer") or 0)
            station = data.get("station")

            # Проверяем предыдущую запись заправки для расчета расхода
            prev_log = await crud.get_last_fuel_log(session, user_id=user_id)
            if prev_log and prev_log.odometer and odometer > prev_log.odometer and liters > 0:
                distance = odometer - prev_log.odometer
                consumption = (liters / distance) * 100
                result_text = f"✅ Записано в базу!\nРасход: {consumption:.1f} л / 100 км"

            await crud.add_fuel_log(
                session=session,
                user_id=user_id,
                liters=liters,
                cost=cost,
                odometer=odometer,
                station_name=station
            )

        elif intent == "service":
            odometer = int(data.get("odometer") or 0)
            title = str(data.get("title") or "Техническое обслуживание")
            cost = float(data["cost"]) if data.get("cost") is not None else None
            notes = data.get("notes")

            await crud.add_service_log(
                session=session,
                user_id=user_id,
                odometer=odometer,
                title=title,
                cost=cost,
                notes=notes
            )

        elif intent == "item_save":
            item_name = str(data.get("item_name") or "Вещь")
            location = str(data.get("location") or "Гараж")

            await crud.upsert_item_location(
                session=session,
                user_id=user_id,
                item_name=item_name,
                location=location
            )

        elif intent == "task_save":
            title = str(data.get("title") or "Задача")
            due_date = data.get("due_date")

            await crud.add_task(
                session=session,
                user_id=user_id,
                title=title,
                due_date=due_date
            )
            due_str = f" (срок: {due_date})" if due_date else ""
            result_text = f"✅ Задача «{title}»{due_str} записана в список дел!"

    # Очищаем FSM состояние
    await state.clear()

    # Редактируем сообщение с карточкой
    await callback.message.edit_text(result_text, reply_markup=None)
    await callback.answer("✅ Успешно сохранено!")


@router.callback_query(F.data == "cancel_entry")
async def process_cancel_entry(callback: CallbackQuery, state: FSMContext):
    """
    Отмена внесения записи.
    Очищает состояние FSM и меняет текст на '❌ Запись отменена'.
    """
    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    await state.clear()
    await callback.message.edit_text("❌ Запись отменена", reply_markup=None)
    await callback.answer("Отменено")
