# bot/handlers/quiz.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import logging

from database.base import AsyncSessionLocal
from database.crud import get_user_or_create
from database.models.user import User
from game.quiz_system import QuizManager
from bot.states import QuizStates
from bot.keyboards import (
    quiz_start_keyboard,
    quiz_options_keyboard,
    quiz_continue_keyboard,
    quiz_result_keyboard
)

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("quiz"))
async def cmd_quiz(message: types.Message):
    """Команда /quiz - вход в викторину"""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, message.from_user.id)

            can_take, minutes_left = await QuizManager.can_take_quiz(user)

            if not can_take:
                await message.answer(
                    f"⏳ <b>Викторина ещё недоступна!</b>\n\n"
                    f"Следующая попытка через {minutes_left} минут.\n\n"
                    f"Возвращайтесь позже!",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
                        ]
                    )
                )
                return

            # Показываем стартовое меню
            text = """
<b>🎯 ВИКТОРИНА "УГАДАЙ АНИМЕ"</b>

<b>📋 Правила:</b>
• Вам будет показано 5 карточек
• Для каждой нужно выбрать аниме из 4 вариантов
• 1 попытка в час

<b>💰 Награды:</b>
• {coins} монет за каждый правильный ответ
• {dust} пыли за каждый правильный ответ
• Бонус {bonus_coins}💰 + {bonus_dust}✨ за все 5 правильных ответов!

<b>🎮 Готовы проверить свои знания?</b>
""".format(
                coins=QuizManager.REWARDS["coins_per_correct"],
                dust=QuizManager.REWARDS["dust_per_correct"],
                bonus_coins=QuizManager.REWARDS["bonus_for_all_correct"]["coins"],
                bonus_dust=QuizManager.REWARDS["bonus_for_all_correct"]["dust"]
            )

            await message.answer(text, reply_markup=quiz_start_keyboard())

    except Exception as e:
        logger.exception(f"Ошибка cmd_quiz: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "quiz_menu")
async def quiz_menu(callback: types.CallbackQuery):
    """Меню викторины из главного меню"""
    await cmd_quiz(callback.message)
    await callback.answer()


@router.callback_query(F.data == "quiz_start")
async def quiz_start(callback: types.CallbackQuery, state: FSMContext):
    """Начать викторину"""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            # Проверяем еще раз (на случай если прошли через меню)
            can_take, minutes_left = await QuizManager.can_take_quiz(user)

            if not can_take:
                await callback.message.edit_text(
                    f"⏳ <b>Викторина ещё недоступна!</b>\n\n"
                    f"Следующая попытка через {minutes_left} минут.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
                        ]
                    )
                )
                await callback.answer()
                return

            # Генерируем вопросы
            questions = await QuizManager.generate_quiz(session)

            # Сохраняем состояние
            await state.update_data(
                questions=questions,
                current_question=0,
                correct_answers=0,
                message_ids=[]  # для хранения ID сообщений, чтобы не засорять чат
            )
            await state.set_state(QuizStates.playing)

            # Показываем первый вопрос
            await show_question(callback.message, 0, questions, state)
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка quiz_start: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


async def show_question(message: types.Message, index: int, questions: list, state: FSMContext):
    """Показать вопрос викторины"""
    question = questions[index]

    text = f"""
<b>🎯 Вопрос {index + 1}/{len(questions)}</b>

<b>🃏 Карточка:</b> {question['card_name']}
<b>👤 Персонаж:</b> {question['character_name'] or 'Неизвестно'}

<b>❓ Из какого аниме этот персонаж?</b>
    """

    # Отправляем фото с клавиатурой
    sent_msg = await message.answer_photo(
        photo=question['image_url'],
        caption=text,
        reply_markup=quiz_options_keyboard(
            question['options'],
            index,
            len(questions)
        )
    )

    # Сохраняем ID сообщения, чтобы потом удалить
    data = await state.get_data()
    message_ids = data.get("message_ids", [])
    message_ids.append(sent_msg.message_id)
    await state.update_data(message_ids=message_ids)


@router.callback_query(F.data.startswith("quiz_answer_"), QuizStates.playing)
async def quiz_answer(callback: types.CallbackQuery, state: FSMContext):
    """Обработка ответа на вопрос"""
    try:
        answer_index = int(callback.data.replace("quiz_answer_", ""))

        data = await state.get_data()
        questions = data["questions"]
        current = data["current_question"]
        correct_answers = data["correct_answers"]

        question = questions[current]

        # Проверяем правильность
        is_correct = (answer_index == question["correct_index"])
        correct_anime = question["anime_name"]

        if is_correct:
            correct_answers += 1
            feedback = "✅ <b>ПРАВИЛЬНО!</b>"
        else:
            feedback = f"❌ <b>НЕПРАВИЛЬНО!</b>\nПравильный ответ: {correct_anime}"

        # Обновляем данные
        await state.update_data(correct_answers=correct_answers)

        # Редактируем сообщение с результатом (без клавиатуры)
        await callback.message.edit_caption(
            caption=f"{callback.message.caption}\n\n{feedback}",
            reply_markup=None
        )

        # Если это был последний вопрос
        if current + 1 >= len(questions):
            # Показываем результат
            await show_quiz_result(callback.message, correct_answers, len(questions), state)
        else:
            # Переходим к следующему вопросу
            await state.update_data(current_question=current + 1)

            # Отправляем кнопку "Дальше"
            await callback.message.answer(
                "➡️ Нажмите для продолжения",
                reply_markup=quiz_continue_keyboard()
            )

        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка quiz_answer: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "quiz_next", QuizStates.playing)
async def quiz_next(callback: types.CallbackQuery, state: FSMContext):
    """Переход к следующему вопросу"""
    try:
        data = await state.get_data()
        questions = data["questions"]
        current = data["current_question"]

        # Удаляем предыдущие сообщения
        for msg_id in data.get("message_ids", []):
            try:
                await callback.bot.delete_message(callback.message.chat.id, msg_id)
            except:
                pass

        # Очищаем список ID
        await state.update_data(message_ids=[])

        # Показываем следующий вопрос
        await show_question(callback.message, current, questions, state)
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка quiz_next: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


async def show_quiz_result(message: types.Message, correct: int, total: int, state: FSMContext):
    """Показать результат викторины"""

    # Рассчитываем награды
    rewards = QuizManager.calculate_rewards(correct)

    # Обновляем пользователя в БД
    async with AsyncSessionLocal() as session:
        user = await get_user_or_create(session, message.chat.id)

        # Начисляем награды
        user.coins += rewards["coins"]
        user.dust += rewards["dust"]
        user.last_quiz_time = datetime.now()

        await session.commit()

    # Формируем текст результата
    bonus_text = "🎉 <b>БОНУС ЗА ВСЕ ПРАВИЛЬНЫЕ!</b>\n" if rewards["bonus"] else ""

    text = f"""
<b>🏁 ВИКТОРИНА ЗАВЕРШЕНА!</b>

📊 <b>Результат:</b> {correct}/{total} правильных ответов

💰 <b>Награды:</b>
• Монеты: +{rewards['coins']}💰
• Пыль: +{rewards['dust']}✨
{bonus_text}
⏳ <b>Следующая попытка:</b> через 1 час

✨ <b>Итоговый баланс:</b>
{user.coins}💰 | {user.dust}✨
    """

    # Отправляем результат
    await message.answer(
        text,
        reply_markup=quiz_result_keyboard(correct, total)
    )

    await state.clear()


@router.callback_query(F.data == "quiz_restart")
async def quiz_restart(callback: types.CallbackQuery, state: FSMContext):
    """Перезапустить викторину (если можно)"""
    await quiz_start(callback, state)


@router.callback_query(F.data == "quiz_again_locked")
async def quiz_again_locked(callback: types.CallbackQuery):
    """Заглушка для кнопки когда нельзя пройти"""
    await callback.answer(
        "⏳ Подождите 1 час до следующей викторины!",
        show_alert=True
    )
    