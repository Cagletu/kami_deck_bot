# bot/handlers/quiz.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import logging
import random
from datetime import datetime, timedelta

from database.base import AsyncSessionLocal
from database.crud import get_user_or_create
from game.quiz_data import quiz_manager, QUIZ_REWARDS

router = Router()
logger = logging.getLogger(__name__)


# Состояния для викторины
class QuizStates(StatesGroup):
    waiting_for_answer = State()
    showing_result = State()


@router.message(Command("quiz"))
async def cmd_quiz(message: types.Message):
    """Начать викторину"""
    try:
        # Создаем клавиатуру с выбором сложности
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢 Лёгкая", callback_data="quiz_easy"),
                InlineKeyboardButton(text="🟡 Средняя", callback_data="quiz_medium"),
                InlineKeyboardButton(text="🔴 Сложная", callback_data="quiz_hard"),
            ],
            [
                InlineKeyboardButton(text="🎲 Случайная", callback_data="quiz_random"),
            ],
            [
                InlineKeyboardButton(text="« Назад", callback_data="back_to_main")
            ]
        ])

        text = """
<b>🎯 АНИМЕ ВИКТОРИНА</b>

Проверь свои знания аниме и получи награды!

<b>🏆 Награды:</b>
🟢 Лёгкая: 10💰 50✨
🟡 Средняя: 25💰 100✨
🔴 Сложная: 50💰 150✨

<b>🎁 Бонус:</b> +25💰 100✨ за все правильные ответы в раунде!

Выбери сложность викторины:
"""

        await message.answer(text, reply_markup=keyboard)

    except Exception as e:
        logger.exception(f"Ошибка cmd_quiz: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data.startswith("quiz_"))
async def start_quiz(callback: CallbackQuery, state: FSMContext):
    """Начать викторину с выбранной сложностью"""
    try:
        difficulty = callback.data.replace("quiz_", "")

        if difficulty == "random":
            difficulties = ["easy", "medium", "hard"]
            difficulty = random.choice(difficulties)

        # Получаем случайный вопрос
        question = quiz_manager.get_random_question(difficulty)

        if not question:
            await callback.answer("❌ Нет вопросов для этой сложности", show_alert=True)
            return

        # Сохраняем данные о викторине
        await state.update_data(
            current_question=question,
            questions_left=4,  # Всего будет 5 вопросов
            correct_answers=0,
            difficulty=difficulty,
            question_ids=[question["id"]]
        )

        # Отправляем первый вопрос
        await send_question(callback.message, question, state)
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка start_quiz: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


async def send_question(message: types.Message, question: dict, state: FSMContext):
    """Отправить вопрос пользователю"""

    # Создаем клавиатуру с вариантами ответов
    keyboard = []
    for i, option in enumerate(question["options"]):
        keyboard.append([
            InlineKeyboardButton(
                text=option,
                callback_data=f"quiz_answer_{i}"
            )
        ])

    # Добавляем кнопку отмены
    keyboard.append([
        InlineKeyboardButton(text="❌ Прервать викторину", callback_data="quiz_cancel")
    ])

    # Эмодзи для сложности
    difficulty_emoji = {
        "easy": "🟢",
        "medium": "🟡",
        "hard": "🔴"
    }.get(question["difficulty"], "🎲")

    text = f"""
{difficulty_emoji} <b>ВОПРОС {5 - len(question.get('options', []))}/5</b>

{question["question"]}

Выбери правильный ответ:
"""

    await message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

    await state.set_state(QuizStates.waiting_for_answer)


@router.callback_query(F.data.startswith("quiz_answer_"), QuizStates.waiting_for_answer)
async def process_answer(callback: CallbackQuery, state: FSMContext):
    """Обработать ответ пользователя"""
    try:
        answer_index = int(callback.data.replace("quiz_answer_", ""))

        data = await state.get_data()
        current_question = data.get("current_question")
        correct_answers = data.get("correct_answers", 0)
        questions_left = data.get("questions_left", 0)
        question_ids = data.get("question_ids", [])
        difficulty = data.get("difficulty", "easy")

        is_correct = (answer_index == current_question["correct"])

        if is_correct:
            correct_answers += 1
            result_text = "✅ <b>Правильно!</b>"
        else:
            correct_option = current_question["options"][current_question["correct"]]
            result_text = f"❌ <b>Неправильно!</b>\nПравильный ответ: {correct_option}"

        # Обновляем состояние
        await state.update_data(
            correct_answers=correct_answers,
            questions_left=questions_left
        )

        if questions_left > 0:
            # Берем следующий вопрос (исключая уже использованные)
            next_question = quiz_manager.get_random_question(difficulty)
            while next_question["id"] in question_ids:
                next_question = quiz_manager.get_random_question(difficulty)

            question_ids.append(next_question["id"])

            await state.update_data(
                current_question=next_question,
                questions_left=questions_left - 1,
                question_ids=question_ids
            )

            # Показываем результат и следующий вопрос
            await callback.message.edit_text(
                f"{result_text}\n\nЗагружаем следующий вопрос..."
            )

            # Отправляем следующий вопрос через небольшую задержку
            import asyncio
            await asyncio.sleep(1)
            await send_question(callback.message, next_question, state)

        else:
            # Викторина завершена
            await end_quiz(callback.message, correct_answers, difficulty, state)

        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка process_answer: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


async def end_quiz(message: types.Message, correct_answers: int, difficulty: str, state: FSMContext):
    """Завершить викторину и начислить награды"""
    try:
        # Получаем пользователя
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, message.chat.id)

            # Базовая награда за сложность
            base_reward = QUIZ_REWARDS.get(difficulty, QUIZ_REWARDS["easy"])

            # Начисляем награды (по 20% за каждый правильный ответ)
            reward_multiplier = correct_answers * 0.2  # 20% за каждый правильный ответ
            coins_reward = int(base_reward["coins"] * (1 + reward_multiplier))
            dust_reward = int(base_reward["dust"] * (1 + reward_multiplier))

            user.coins += coins_reward
            user.dust += dust_reward

            # Бонус за все правильные ответы
            perfect_bonus = ""
            if correct_answers == 5:
                perfect = QUIZ_REWARDS["perfect"]
                user.coins += perfect["coins"]
                user.dust += perfect["dust"]
                perfect_bonus = f"\n\n🎁 <b>БОНУС ЗА ИДЕАЛЬНЫЙ РАУНД!</b>\n+{perfect['coins']}💰 +{perfect['dust']}✨"

            await session.commit()

        # Формируем результат
        result_text = f"""
<b>🎯 ВИКТОРИНА ЗАВЕРШЕНА!</b>

✅ Правильных ответов: {correct_answers}/5
{'🏆 Отличный результат!' if correct_answers >= 4 else '📚 Можно лучше!'}

<b>💰 Награды:</b>
+{coins_reward}💰 монет
+{dust_reward}✨ пыли
{perfect_bonus}

Выбери действие:
"""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Ещё раз", callback_data=f"quiz_{difficulty}"),
                InlineKeyboardButton(text="🎲 Другая сложность", callback_data="quiz_random"),
            ],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")
            ]
        ])

        await message.edit_text(result_text, reply_markup=keyboard)
        await state.clear()

    except Exception as e:
        logger.exception(f"Ошибка end_quiz: {e}")
        await message.edit_text("❌ Произошла ошибка при начислении наград")


@router.callback_query(F.data == "quiz_cancel")
async def cancel_quiz(callback: CallbackQuery, state: FSMContext):
    """Прервать викторину"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Викторина прервана",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")]
        ])
    )
    await callback.answer()