from aiogram.fsm.state import State, StatesGroup


class ExpeditionStates(StatesGroup):
    """Состояния для процесса экспедиции"""

    choosing_cards = State()  # Выбор карт
    confirm = State()  # Подтверждение
