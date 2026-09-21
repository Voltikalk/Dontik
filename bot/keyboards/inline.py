from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData


class ActionCallback(CallbackData, prefix="act"):
    action: str


class ConfirmCallback(CallbackData, prefix="cnf"):
    action: str  # fuel, service, item
    draft_id: str


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главная инлайн-клавиатура быстрого доступа."""
    buttons = [
        [
            InlineKeyboardButton(text="⛽ Заправки (история)", callback_data=ActionCallback(action="history_fuel").pack()),
            InlineKeyboardButton(text="🔧 Сервис и ТО", callback_data=ActionCallback(action="history_service").pack()),
        ],
        [
            InlineKeyboardButton(text="📦 Вещи в гараже", callback_data=ActionCallback(action="list_items").pack()),
            InlineKeyboardButton(text="📊 Сводка и расходы", callback_data=ActionCallback(action="summary_stats").pack()),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_confirm_keyboard(action_type: str, draft_id: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения AI-распознанных данных."""
    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Записать в журнал",
                callback_data=ConfirmCallback(action=action_type, draft_id=draft_id).pack()
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=ActionCallback(action=f"cancel_{draft_id}").pack()
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_entry_confirm_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-кнопки подтверждения записи (confirm_entry / cancel_entry)."""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_entry"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_entry"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

