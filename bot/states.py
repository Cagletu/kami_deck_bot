#bot/states.py
from aiogram.fsm.state import State, StatesGroup


class ExpeditionStates(StatesGroup):
    """Состояния для процесса экспедиции"""

    choosing_cards = State()  # Выбор карт
    confirm = State()  # Подтверждение


class QuizStates(StatesGroup):
    """Состояния для викторины"""

    playing = State()  # Активная викторина
    showing_result = State()  # Показ результата
