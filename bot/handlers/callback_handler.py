import re
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.database.db import get_session
from bot.database import crud
from bot.services.draft_store import pop_draft
from bot.keyboards.inline import get_tasks_keyboard

logger = logging.getLogger(__name__)

router = Router(name="callback_handler_router")


def parse_card_text(text: str) -> tuple[str | None, dict]:
    """
    Резервный парсинг данных прямо из текста карточки в Telegram.
    Используется, если FSM или временное хранилище было очищено/перезапущено.
    """
    if not text:
        return None, {}

    # 1. Задача
    if "Новая задача" in text or "список дел" in text or "Дело:" in text:
        title_m = re.search(r'Дело:\*?\s*([^\n\*_]+)', text)
        due_m = re.search(r'Срок:\*?\s*([^\n\*_]+)', text)
        title = title_m.group(1).strip() if title_m else "Задача"
        due_date = due_m.group(1).strip() if due_m else None
        return "task_save", {"title": title, "due_date": due_date}

    # 2. Заправка
    if "заправка" in text.lower() or "Литры:" in text:
        liters_m = re.search(r'Литры:\*?\s*([0-9.,]+)', text)
        cost_m = re.search(r'Сумма:\*?\s*([0-9\s.,]+)', text)
        odo_m = re.search(r'Пробег:\*?\s*([0-9\s.,]+)', text)
        st_m = re.search(r'АЗС:\*?\s*([^\n\*_]+)', text)

        liters = float(liters_m.group(1).replace(",", ".")) if liters_m else 0.0
        cost_str = cost_m.group(1).replace(" ", "").replace("₽", "").replace(",", ".") if cost_m else "0"
        cost = float(cost_str) if cost_str else 0.0
        odo_str = odo_m.group(1).replace(" ", "").replace("км", "") if odo_m else "0"
        odo = int(odo_str) if odo_str.isdigit() else 0
        station = st_m.group(1).strip() if st_m and "не указана" not in st_m.group(1) else None
        return "fuel", {"liters": liters, "cost": cost, "odometer": odo, "station": station}

    # 3. Сервис / ремонт
    if "обслуживание" in text.lower() or "ремонт" in text.lower() or "Работы:" in text:
        title_m = re.search(r'Работы:\*?\s*([^\n\*_]+)', text)
        odo_m = re.search(r'Пробег:\*?\s*([0-9\s.,]+)', text)
        cost_m = re.search(r'Стоимость:\*?\s*([0-9\s.,]+)', text)
        notes_m = re.search(r'Заметки:\*?\s*([^\n\*_]+)', text)

        title = title_m.group(1).strip() if title_m else "Техническое обслуживание"
        odo_str = odo_m.group(1).replace(" ", "").replace("км", "") if odo_m else "0"
        odo = int(odo_str) if odo_str.isdigit() else 0
        cost = float(cost_m.group(1).replace(" ", "").replace("₽", "").replace(",", ".")) if cost_m and "не указано" not in cost_m.group(1) else None
        notes = notes_m.group(1).strip() if notes_m else None
        return "service", {"title": title, "odometer": odo, "cost": cost, "notes": notes}

    # 4. Вещь
    if "местоположение" in text.lower() or "Предмет:" in text:
        item_m = re.search(r'Предмет:\*?\s*([^\n\*_]+)', text)
        loc_m = re.search(r'Где лежит:\*?\s*([^\n\*_]+)', text)
        item_name = item_m.group(1).strip() if item_m else "Вещь"
        location = loc_m.group(1).strip() if loc_m else "Гараж"
        return "item_save", {"item_name": item_name, "location": location}

    return None, {}


@router.callback_query(F.data.startswith("confirm_entry"))
async def process_confirm_entry(callback: CallbackQuery, state: FSMContext):
    """
    Подтверждение и сохранение записи в SQLite с многоуровневым поиском данных:
    1. По draft_id из callback_data.
    2. Из FSMContext.
    3. Резервный парсинг прямо из текста сообщения карточки.
    """
    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    user_id = callback.from_user.id
    draft_id = callback.data.split(":", 1)[1] if ":" in callback.data else None

    intent = None
    data = {}

    # Уровень 1: Проверяем хранилище черновиков по draft_id
    if draft_id:
        draft = pop_draft(draft_id)
        if draft:
            intent = draft.get("intent")
            data = draft.get("data", {})

    # Уровень 2: Проверяем FSM
    if not intent or not data:
        state_data = await state.get_data()
        if state_data.get("intent"):
            intent = state_data.get("intent")
            data = state_data.get("payload") or state_data.get("data") or {}
            if not data:
                data = {
                    k: v for k, v in state_data.items()
                    if k not in ("intent", "transcript", "payload", "draft_id")
                }

    # Уровень 3: Резервный разбор текста сообщения карточки
    if not intent or not data:
        card_text = callback.message.text or callback.message.caption or ""
        parsed_intent, parsed_data = parse_card_text(card_text)
        if parsed_intent and parsed_data:
            intent = parsed_intent
            data = parsed_data

    # Если все уровни не дали результата
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
    try:
        await callback.message.edit_text(result_text, reply_markup=None)
    except Exception:
        pass
    await callback.answer("✅ Успешно сохранено!")


@router.callback_query(F.data.startswith("cancel_entry"))
async def process_cancel_entry(callback: CallbackQuery, state: FSMContext):
    """
    Отмена внесения записи.
    Очищает черновик и FSM, меняет текст на '❌ Запись отменена'.
    """
    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    draft_id = callback.data.split(":", 1)[1] if ":" in callback.data else None
    if draft_id:
        pop_draft(draft_id)

    await state.clear()
    try:
        await callback.message.edit_text("❌ Запись отменена", reply_markup=None)
    except Exception:
        pass
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("done_task:"))
async def process_done_task(callback: CallbackQuery):
    """Отмечает задачу как выполненную прямо по нажатию кнопки в списке задач."""
    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    task_id_str = callback.data.split(":", 1)[1]
    if not task_id_str.isdigit():
        await callback.answer()
        return

    task_id = int(task_id_str)
    user_id = callback.from_user.id

    async with get_session() as session:
        success = await crud.complete_task(session, user_id=user_id, task_id=task_id)
        if success:
            tasks = await crud.get_active_tasks(session, user_id=user_id)
            if tasks:
                lines = ["📋 <b>Твой актуальный список дел и задач:</b>\n"]
                for idx, t in enumerate(tasks, 1):
                    due_str = f" <i>(срок: {t.due_date})</i>" if t.due_date else ""
                    lines.append(f"{idx}. <b>{t.title}</b>{due_str}")
                kb = get_tasks_keyboard(tasks)
                await callback.message.edit_text("\n".join(lines), reply_markup=kb, parse_mode="HTML")
            else:
                await callback.message.edit_text(
                    "🎉 <b>Все задачи выполнены! Отличная работа.</b>",
                    reply_markup=None,
                    parse_mode="HTML"
                )
            await callback.answer("✅ Задача выполнена!")
        else:
            await callback.answer("Задача уже была отмечена или удалена.", show_alert=True)
