# game/quiz_system.py
import random
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.card import Card
from database.models.user import User

class QuizManager:
    """Менеджер викторины"""

    # Количество вопросов в викторине
    QUESTIONS_COUNT = 5

    # Количество вариантов ответа на вопрос
    OPTIONS_COUNT = 4

    # Награды (за каждый правильный ответ)
    REWARDS = {
        "coins_per_correct": 25,  # 50 монет за каждый правильный ответ
        "dust_per_correct": 50,     # 5 пыли за каждый правильный ответ
        "bonus_for_all_correct": {  # Бонус если ответил на все правильно
            "coins": 50,
            "dust": 50
        }
    }

    @staticmethod
    async def can_take_quiz(user: User) -> Tuple[bool, Optional[int]]:
        """Проверить, может ли пользователь пройти викторину"""
        if not user.last_quiz_time:
            return True, None

        # Проверяем, прошел ли час
        time_diff = datetime.now() - user.last_quiz_time
        if time_diff.total_seconds() >= 3600:  # 1 час
            return True, None
        else:
            # Сколько минут осталось
            minutes_left = 60 - (time_diff.total_seconds() // 60)
            return False, int(minutes_left)

    @staticmethod
    async def generate_quiz(session: AsyncSession) -> List[Dict]:
        """Сгенерировать вопросы для викторины"""

        # Получаем случайные карточки
        # Используем TABLESAMPLE для производительности (35000+ карточек)
        result = await session.execute(
            select(Card)
            .where(Card.anime_name.isnot(None))  # Только карточки с аниме
            .order_by(func.random())
            .limit(QuizManager.QUESTIONS_COUNT)
        )
        cards = result.scalars().all()

        if len(cards) < QuizManager.QUESTIONS_COUNT:
            # Если мало карточек с аниме, берем что есть
            result = await session.execute(
                select(Card)
                .order_by(func.random())
                .limit(QuizManager.QUESTIONS_COUNT)
            )
            cards = result.scalars().all()

        questions = []
        for card in cards:
            # Получаем 3 случайных аниме для вариантов ответа
            wrong_answers = await QuizManager._get_random_anime_names(
                session, 
                exclude=card.anime_name,
                count=QuizManager.OPTIONS_COUNT - 1
            )

            # Формируем варианты ответа
            options = [card.anime_name] + wrong_answers
            random.shuffle(options)  # Перемешиваем, чтобы правильный не был первым

            # Находим индекс правильного ответа
            correct_index = options.index(card.anime_name)

            questions.append({
                "card_id": card.id,
                "card_name": card.card_name,
                "character_name": card.character_name,
                "image_url": card.original_url,
                "options": options,
                "correct_index": correct_index,
                "anime_name": card.anime_name  # для проверки
            })

        return questions

    @staticmethod
    async def _get_random_anime_names(session: AsyncSession, exclude: str, count: int) -> List[str]:
        """Получить случайные названия аниме"""
        # Получаем уникальные названия аниме из базы
        result = await session.execute(
            select(Card.anime_name)
            .where(Card.anime_name.isnot(None))
            .where(Card.anime_name != exclude)
            .distinct()
            .order_by(func.random())
            .limit(count)
        )
        names = [row[0] for row in result.all() if row[0]]

        # Если недостаточно уникальных, добираем заглушками
        while len(names) < count:
            names.append("Неизвестное аниме")

        return names

    @staticmethod
    def calculate_rewards(correct_answers: int) -> Dict:
        """Рассчитать награды"""
        coins = correct_answers * QuizManager.REWARDS["coins_per_correct"]
        dust = correct_answers * QuizManager.REWARDS["dust_per_correct"]

        if correct_answers == QuizManager.QUESTIONS_COUNT:
            coins += QuizManager.REWARDS["bonus_for_all_correct"]["coins"]
            dust += QuizManager.REWARDS["bonus_for_all_correct"]["dust"]

        return {
            "coins": coins,
            "dust": dust,
            "correct_answers": correct_answers,
            "total_questions": QuizManager.QUESTIONS_COUNT,
            "bonus": correct_answers == QuizManager.QUESTIONS_COUNT
        }
        