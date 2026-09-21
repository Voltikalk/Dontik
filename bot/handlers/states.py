from aiogram.fsm.state import State, StatesGroup


class GarageEntryState(StatesGroup):
    """Состояние ожидания подтверждения распознанной записи."""
    waiting_confirmation = State()
