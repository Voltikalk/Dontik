"""Инлайн-клавиатуры бота и их callback_data."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData

from bot.emojis import (
    ID_DROP,
    ID_WRENCH,
    ID_BOX,
    ID_CHART,
    ID_CHECK,
    ID_CROSS,
    ID_PEN,
    ID_NOTE,
    ID_REPEAT,
    ID_SEARCH,
    ID_INBOX,
    ID_BOT,
    ID_PIN,
)

MAX_TASK_BUTTONS = 6


class ActionCallback(CallbackData, prefix="act"):
    """Действия главного меню (act:...)."""
    action: str


class EntryCallback(CallbackData, prefix="ent"):
    """Действия карточки подтверждения (ent:...)."""
    action: str  # save | cancel | edit
    draft_id: str


class EditFieldCallback(CallbackData, prefix="edf"):
    """Выбор поля для правки прямо в карточке (edf:...)."""
    field: str
    draft_id: str


class TaskCallback(CallbackData, prefix="tsk"):
    """Действия со списком задач (tsk:...)."""
    action: str  # done | undo | done_all
    task_id: str = "0"


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню быстрого доступа."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Задачи",
                callback_data=ActionCallback(action="tasks").pack(),
                icon_custom_emoji_id=ID_NOTE,
            ),
            InlineKeyboardButton(
                text="Сводка",
                callback_data=ActionCallback(action="summary_stats").pack(),
                icon_custom_emoji_id=ID_CHART,
            ),
        ],
        [
            InlineKeyboardButton(
                text="Заправки",
                callback_data=ActionCallback(action="history_fuel").pack(),
                icon_custom_emoji_id=ID_DROP,
            ),
            InlineKeyboardButton(
                text="Сервис",
                callback_data=ActionCallback(action="history_service").pack(),
                icon_custom_emoji_id=ID_WRENCH,
            ),
        ],
        [
            InlineKeyboardButton(
                text="Вещи",
                callback_data=ActionCallback(action="list_items").pack(),
                icon_custom_emoji_id=ID_BOX,
            ),
            InlineKeyboardButton(
                text="Поиск вещи",
                callback_data=ActionCallback(action="find_item").pack(),
                icon_custom_emoji_id=ID_SEARCH,
            ),
        ],
        [
            InlineKeyboardButton(
                text="Почта",
                callback_data=ActionCallback(action="mail").pack(),
                icon_custom_emoji_id=ID_INBOX,
            ),
            InlineKeyboardButton(
                text="Субагенты",
                callback_data=ActionCallback(action="agent").pack(),
                icon_custom_emoji_id=ID_BOT,
            ),
        ],
        [
            InlineKeyboardButton(
                text="Помощь",
                callback_data=ActionCallback(action="help").pack(),
                icon_custom_emoji_id=ID_PIN,
            ),
        ],
    ])


def get_entry_confirm_keyboard(draft_id: str, intent: str = "") -> InlineKeyboardMarkup:
    """Карточка распознанных данных: сохранить / поправить / отмена."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Записать",
                callback_data=EntryCallback(action="save", draft_id=draft_id).pack(),
                icon_custom_emoji_id=ID_CHECK,
            ),
            InlineKeyboardButton(
                text="Поправить",
                callback_data=EntryCallback(action="edit", draft_id=draft_id).pack(),
                icon_custom_emoji_id=ID_PEN,
            ),
        ],
        [
            InlineKeyboardButton(
                text="Отмена",
                callback_data=EntryCallback(action="cancel", draft_id=draft_id).pack(),
                icon_custom_emoji_id=ID_CROSS,
            ),
        ],
    ])


_EDIT_FIELDS: dict[str, list[tuple[str, str]]] = {
    "fuel": [("liters", "Литры"), ("cost", "Сумма"), ("odometer", "Пробег"), ("station", "АЗС")],
    "service": [("title", "Работа"), ("cost", "Стоимость"), ("odometer", "Пробег")],
    "item_save": [("item_name", "Предмет"), ("location", "Где лежит")],
    "task_save": [("title", "Дело"), ("due_date", "Срок")],
}


def get_edit_field_keyboard(intent: str, draft_id: str) -> InlineKeyboardMarkup:
    """Показывает кнопки редактирования конкретных полей карточки."""
    fields = _EDIT_FIELDS.get(intent, [("title", "Значение")])
    buttons = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=EditFieldCallback(field=field, draft_id=draft_id).pack(),
                icon_custom_emoji_id=ID_PEN,
            )
        ]
        for field, label in fields
    ]
    buttons.append([
        InlineKeyboardButton(
            text="Готово, всё верно",
            callback_data=EntryCallback(action="save", draft_id=draft_id).pack(),
            icon_custom_emoji_id=ID_CHECK,
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_tasks_keyboard(tasks, show_done_all: bool = True) -> InlineKeyboardMarkup | None:
    """Клавиатура списка задач: отметка выполнения + «всё выполнено»."""
    if not tasks:
        return None

    buttons = [
        [
            InlineKeyboardButton(
                text=_short(t.title, 26),
                callback_data=TaskCallback(action="done", task_id=str(t.id)).pack(),
                icon_custom_emoji_id=ID_CHECK,
            )
        ]
        for t in tasks[:MAX_TASK_BUTTONS]
    ]

    if show_done_all:
        buttons.append([
            InlineKeyboardButton(
                text="✅ Всё выполнено",
                callback_data=TaskCallback(action="done_all").pack(),
                icon_custom_emoji_id=ID_CHECK,
            ),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_undo_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Предлагает вернуть только что закрытую задачу."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="↩️ Вернуть",
                callback_data=TaskCallback(action="undo", task_id=str(task_id)).pack(),
                icon_custom_emoji_id=ID_REPEAT,
            ),
        ],
    ])


def _short(text: str, limit: int) -> str:
    """Обрезает текст кнопки так, чтобы Telegram не отверг её по длине."""
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"