"""Состояния FSM бота."""

from aiogram.fsm.state import State, StatesGroup


class GarageEntryState(StatesGroup):
    """Ожидание подтверждения распознанной записи."""
    waiting_confirmation = State()


class EditEntryState(StatesGroup):
    """Пользователь правит конкретное поле карточки перед сохранением."""
    waiting_field = State()


class FindItemState(StatesGroup):
    """Пользователь ввёл поисковый запрос вещи с кнопки «Поиск вещи»."""
    waiting_query = State()