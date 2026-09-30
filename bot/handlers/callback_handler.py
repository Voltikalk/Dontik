"""
Обработка всех inline-кнопок: меню, карточки подтверждения, правка полей, задачи.
"""

import logging
import re

from aiogram import Router, html
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import crud
from bot.database.db import get_session
from bot.emojis import E_ALERT, E_CHECK, E_CROSS, E_LIST, E_PIN, E_SEARCH, E_WRENCH
from bot.handlers.input_handler import send_tasks_list
from bot.handlers.states import EditEntryState, FindItemState
from bot.keyboards.inline import (
    ActionCallback,
    EditFieldCallback,
    EntryCallback,
    TaskCallback,
    get_edit_field_keyboard,
    get_main_menu_keyboard,
    get_undo_task_keyboard,
)
from bot.services import draft_store
from bot.services.dates import resolve_due
from bot.services.formatters import (
    format_all_items_list,
    format_confirmed,
    format_fuel_history,
    format_search_prompt,
    format_service_history,
    format_stats_summary,
    fmt_money,
)

logger = logging.getLogger(__name__)

router = Router(name="callback_handler_router")

# Поля карточки, в которые можно попасть кнопкой «Поправить».
_FIELD_LABELS = {
    "liters": "Литры",
    "cost": "Стоимость",
    "odometer": "Пробег",
    "station": "АЗС",
    "title": "Название",
    "location": "Место хранения",
    "due_date": "Срок",
    "item_name": "Предмет",
}
_NUMERIC_FIELDS = {"liters", "cost", "odometer"}


# --- Резервный разбор карточки из текста сообщения ---

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: str) -> str:
    """Убирает HTML-теги и эмодзи-теги, приводит к чистому тексту."""
    return _TAG_RE.sub("", value or "").replace("", "").strip()


def parse_card_text(text: str) -> tuple[str | None, dict]:
    """
    Аварийный разбор данных прямо из текста карточки в Telegram.

    Нужен, когда черновик потерялся (перезапуск бота). Работает с тем HTML,
    который реально отправляет бот: «• <b>Литры:</b> <code>42.5 л</code>».
    """
    if not text:
        return None, {}

    plain = _clean(text)
    lowered = plain.lower()

    def grab(label: str) -> str | None:
        # «Литры: 42.5 л» -> «42.5 л»
        match = re.search(rf"{label}\s*:\s*(.+)", plain)
        return match.group(1).strip() if match else None

    def grab_num(label: str) -> float | None:
        raw = grab(label)
        if not raw:
            return None
        match = re.search(r"-?\d[\d\s]*(?:[.,]\d+)?", raw)
        if not match:
            return None
        cleaned = match.group(0).replace(" ", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    if "новая задача" in lowered or "дело:" in lowered:
        return "task_save", {"title": grab("Дело"), "due_date": grab("Срок")}

    if "заправка" in lowered or "литры:" in lowered:
        station = grab("АЗС")
        return "fuel", {
            "liters": grab_num("Литры"),
            "cost": grab_num("Сумма"),
            "odometer": int(grab_num("Пробег") or 0),
            "station": None if not station or "не указан" in station.lower() else station,
        }

    if "обслуживание" in lowered or "ремонт" in lowered or "работа:" in lowered:
        cost = grab_num("Стоимость")
        return "service", {
            "title": grab("Работа"),
            "cost": cost,
            "odometer": int(grab_num("Пробег") or 0),
            "notes": grab("Заметки"),
        }

    if "местоположение" in lowered or "предмет:" in lowered:
        return "item_save", {"item_name": grab("Предмет"), "location": grab("Где лежит")}

    return None, {}


async def _resolve_draft(callback: CallbackQuery, draft_id: str) -> tuple[str | None, dict]:
    """Ищет данные карточки: черновик -> FSM -> текст сообщения."""
    # 1. Черновик (основной путь)
    draft = draft_store.get_draft(draft_id) if draft_id else None
    if draft:
        return draft.get("intent"), dict(draft.get("data") or {})

    # 2. Текст самой карточки (пережил перезапуск бота)
    if callback.message:
        text = callback.message.text or callback.message.caption or ""
        intent, data = parse_card_text(text)
        if intent:
            logger.info("Восстановил карточку из текста: intent=%s", intent)
            return intent, data

    return None, {}


async def _save_entry(callback: CallbackQuery, state: FSMContext, draft_id: str) -> str:
    """Сохраняет запись в БД и возвращает текст подтверждения."""
    intent, data = await _resolve_draft(callback, draft_id)
    if not intent:
        return ""

    user_id = callback.from_user.id
    consumption = None

    async with get_session() as session:
        if intent == "fuel":
            liters = float(data.get("liters") or 0.0)
            cost = float(data.get("cost") or 0.0)
            odometer = int(data.get("odometer") or 0)

            prev = await crud.get_last_fuel_log(session, user_id=user_id)
            if prev and prev.odometer and odometer > prev.odometer:
                distance = odometer - prev.odometer
                if liters > 0 and 0 < distance <= 3000:
                    consumption = round(liters / distance * 100, 1)

            await crud.add_fuel_log(
                session=session,
                user_id=user_id,
                liters=liters,
                cost=cost,
                odometer=odometer,
                station_name=data.get("station"),
            )

        elif intent == "service":
            cost = data.get("cost")
            await crud.add_service_log(
                session=session,
                user_id=user_id,
                odometer=int(data.get("odometer") or 0),
                title=str(data.get("title") or "Техническое обслуживание"),
                cost=float(cost) if cost is not None else None,
                notes=data.get("notes"),
            )

        elif intent == "item_save":
            await crud.upsert_item_location(
                session=session,
                user_id=user_id,
                item_name=str(data.get("item_name") or "Вещь"),
                location=str(data.get("location") or "Гараж"),
            )

        elif intent == "task_save":
            raw_due = data.get("due_date")
            await crud.add_task(
                session=session,
                user_id=user_id,
                title=str(data.get("title") or "Задача"),
                due_date=str(raw_due) if raw_due else None,
                due_at=resolve_due(data.get("due_at"), str(raw_due) if raw_due else None),
            )

    draft_store.pop_draft(draft_id)
    return format_confirmed(intent, data, consumption)


# --- Карточка: сохранить / отмена / поправить ---

@router.callback_query(EntryCallback.filter())
async def handle_entry(callback: CallbackQuery, callback_data: EntryCallback, state: FSMContext):
    action = callback_data.action
    draft_id = callback_data.draft_id

    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    if action == "cancel":
        draft_store.pop_draft(draft_id)
        await state.clear()
        await callback.answer("Отменено")
        await _safe_edit(callback.message, f"{E_CROSS} <b>Отменено</b>", reply_markup=None)
        return

    if action == "edit":
        draft = draft_store.get_draft(draft_id)
        if not draft:
            await callback.answer("Карточка устарела — скажи это ещё раз", show_alert=True)
            await _safe_edit(callback.message, f"{E_ALERT} Карточка устарела. Скажи это ещё раз — сделаю новую.", reply_markup=None)
            return

        await state.set_state(EditEntryState.waiting_field)
        await state.update_data(draft_id=draft_id, intent=draft.get("intent"), editing_field="")
        await callback.answer()
        await callback.message.answer(
            f"{E_PIN} <b>Что поправить?</b>\n\nНажми поле, потом пришли новое значение текстом.",
            reply_markup=get_edit_field_keyboard(draft.get("intent", ""), draft_id),
            parse_mode=ParseMode.HTML,
        )
        return

    # action == "save"
    result_text = await _save_entry(callback, state, draft_id)
    if not result_text:
        await callback.answer("Карточка устарела или уже сохранена", show_alert=True)
        await _safe_edit(callback.message, f"{E_ALERT} Карточка уже неактуальна.", reply_markup=None)
        return

    await state.clear()
    await callback.answer("Записано")
    await _safe_edit(callback.message, result_text, reply_markup=None)


@router.callback_query(EditFieldCallback.filter())
async def handle_edit_field_pick(callback: CallbackQuery, callback_data: EditFieldCallback, state: FSMContext):
    """Пользователь выбрал, какое поле карточки хочет исправить."""
    field = callback_data.field
    label = _FIELD_LABELS.get(field, field)

    await state.set_state(EditEntryState.waiting_field)
    await state.update_data(draft_id=callback_data.draft_id, editing_field=field)

    hint = " (только число)" if field in _NUMERIC_FIELDS else ""
    await callback.answer()
    await callback.message.answer(
        f"{E_PIN} Пришли новое значение для <b>{html.quote(label)}</b>{hint}.\n"
        f"Пример: <i>2500</i>",
        parse_mode=ParseMode.HTML,
    )


# --- Задачи ---

@router.callback_query(TaskCallback.filter())
async def handle_task(callback: CallbackQuery, callback_data: TaskCallback):
    action = callback_data.action
    user_id = callback.from_user.id

    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    if action == "done_all":
        async with get_session() as session:
            closed = await crud.complete_all_tasks(session, user_id=user_id)
        await callback.answer(f"Закрыто задач: {closed}")
        await callback.message.answer(
            f"{E_CHECK} <b>Все задачи закрыты</b> — отмечено {closed}.\n"
            f"Открывай новые дела командой /tasks.",
            parse_mode=ParseMode.HTML,
        )
        return

    if not callback_data.task_id.isdigit():
        await callback.answer()
        return

    task_id = int(callback_data.task_id)

    if action == "undo":
        async with get_session() as session:
            ok = await crud.uncomplete_task(session, user_id=user_id, task_id=task_id)
        await callback.answer("Вернул в список" if ok else "Задача и так активна", show_alert=not ok)
        if ok:
            await send_tasks_list(callback.message, user_id)
        return

    # action == "done"
    async with get_session() as session:
        ok = await crud.complete_task(session, user_id=user_id, task_id=task_id)
        title = None
        if ok:
            task = await crud.get_task(session, user_id=user_id, task_id=task_id)
            title = task.title if task else None

    if not ok:
        await callback.answer("Уже выполнено", show_alert=True)
        return

    await callback.answer("Готово")

    await send_tasks_list(callback.message, user_id, edit=True)
    if title:
        await callback.message.answer(
            f"{E_CHECK} Закрыто: <b>{html.quote(title)}</b>",
            reply_markup=get_undo_task_keyboard(task_id),
            parse_mode=ParseMode.HTML,
        )


# --- Главное меню ---

@router.callback_query(ActionCallback.filter())
async def handle_action(callback: CallbackQuery, callback_data: ActionCallback, state: FSMContext):
    action = callback_data.action
    user_id = callback.from_user.id

    if not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    if action == "tasks":
        await callback.answer()
        await send_tasks_list(callback.message, user_id)

    elif action == "summary_stats":
        async with get_session() as session:
            fuel = await crud.get_fuel_stats(session, user_id=user_id)
            service = await crud.get_service_stats(session, user_id=user_id)
            consumption = await crud.get_avg_consumption(session, user_id=user_id)
        fuel["avg_consumption"] = consumption or 0.0

        fuel_block = format_stats_summary(fuel)
        service_block = (
            f"{E_WRENCH} <b>Сервис и ремонты</b>\n"
            f"• Записей: <code>{service['count']}</code>\n"
            f"• Потрачено: <code>{fmt_money(service['total_cost'])}</code>"
        )
        await callback.answer()
        await callback.message.answer(
            f"{fuel_block}\n\n{service_block}",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif action == "history_fuel":
        async with get_session() as session:
            logs = await crud.get_recent_fuel_logs(session, user_id=user_id, limit=10)
        await callback.answer()
        await callback.message.answer(
            format_fuel_history(logs),
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif action == "history_service":
        async with get_session() as session:
            logs = await crud.get_recent_service_logs(session, user_id=user_id, limit=10)
        await callback.answer()
        await callback.message.answer(
            format_service_history(logs),
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif action == "list_items":
        async with get_session() as session:
            items = await crud.list_all_items(session, user_id=user_id)
        await callback.answer()
        await callback.message.answer(
            format_all_items_list(items),
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    elif action == "find_item":
        await state.set_state(FindItemState.waiting_query)
        await callback.answer()
        await callback.message.answer(format_search_prompt(), parse_mode=ParseMode.HTML)

    elif action == "mail":
        from bot.handlers.email_handler import cmd_check_mail

        await callback.answer()
        await cmd_check_mail(callback.message)

    elif action == "agent":
        await callback.answer()
        await callback.message.answer(
            f"{E_SEARCH} <b>Команда субагентов</b>\n\n"
            f"Отправь команду вида:\n"
            f"<code>/agent Замена сцепления ВАЗ 2121: регламент, цены, пошаговый план</code>\n\n"
            f"Бот подключит поисковик, техэксперта, смету и планировщика.",
            parse_mode=ParseMode.HTML,
        )

    elif action == "help":
        from bot.handlers.general_handler import cmd_help

        await callback.answer()
        await cmd_help(callback.message)

    elif action == "new":
        await callback.answer()
        await callback.message.answer(
            f"{E_LIST} <b>Что делаем?</b>\n\n"
            f"Просто скажи или напиши:\n"
            f"• <i>запиши купить масло и фильтр</i>\n"
            f"• <i>заправил 40 литров на 2400, пробег 152000</i>\n"
            f"• <i>положил ключ на 13 в синий ящик</i>\n"
            f"• <i>реши уравнение x² + 5x − 6 = 0</i>",
            parse_mode=ParseMode.HTML,
        )

    else:
        await callback.answer("Кнопка устарела, открой /start", show_alert=True)


async def _safe_edit(message: Message, text: str, reply_markup=None) -> None:
    """Редактирует сообщение, при неудаче отправляет новое (Telegram мог запретить правку)."""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось отредактировать сообщение (%s), отправляю новое", exc)
        try:
            await message.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception:  # noqa: BLE001
            pass