from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Tuple
import logging

from database.models.user_card import UserCard
from database.models.card import Card
from database.models.user import User
from database.base import AsyncSessionLocal
from game.constants import DUST_PER_RARITY, UPGRADE_COST_PER_LEVEL, MAX_CARD_LEVEL

logger = logging.getLogger(__name__)


async def get_user_card_detail(
    user_card_id: int, user_id: int
) -> Optional[Tuple[UserCard, Card]]:
    """Получить детальную информацию о карте пользователя"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserCard, Card)
            .join(Card, UserCard.card_id == Card.id)
            .where(and_(UserCard.id == user_card_id, UserCard.user_id == user_id))
        )
        return result.first()


async def upgrade_user_card(user_card_id: int, user_id: int) -> Optional[UserCard]:
    """Улучшить карту на 1 уровень"""
    async with AsyncSessionLocal() as session:
        # Получаем карту с проверкой принадлежности пользователю
        result = await session.execute(
            select(UserCard, Card)
            .join(Card, UserCard.card_id == Card.id)
            .where(and_(UserCard.id == user_card_id, UserCard.user_id == user_id))
        )
        data = result.first()

        if not data:
            raise ValueError("Карта не найдена или не принадлежит вам")

        user_card, card = data

        # Проверка максимального уровня
        if user_card.level >= MAX_CARD_LEVEL:
            raise ValueError(
                f"Карта уже достигла максимального уровня {MAX_CARD_LEVEL}"
            )

        # Расчет стоимости улучшения
        rarity_multiplier = DUST_PER_RARITY.get(card.rarity, 10)
        upgrade_cost = UPGRADE_COST_PER_LEVEL * rarity_multiplier

        # Получаем пользователя для проверки пыли
        user = await session.get(User, user_id)
        if user.dust < upgrade_cost:
            raise ValueError(
                f"Недостаточно пыли! Нужно: {upgrade_cost}, у вас: {user.dust}"
            )

        # Снимаем пыль
        user.dust -= upgrade_cost
        user.total_cards_upgraded += 1

        # Увеличиваем уровень
        user_card.level += 1
        user_card.times_upgraded += 1

        # Пересчитываем характеристики
        from game.upgrade_calculator import calculate_stats_for_level

        new_stats = calculate_stats_for_level(card, user_card.level)

        user_card.current_power = new_stats["power"]
        user_card.current_health = new_stats["health"]
        user_card.current_attack = new_stats["attack"]
        user_card.current_defense = new_stats["defense"]

        await session.commit()
        await session.refresh(user_card)

        logger.info(f"✅ Карта {card.card_name} улучшена до {user_card.level} уровня")

        return user_card


async def toggle_favorite(user_card_id: int, user_id: int) -> bool:
    """Добавить/убрать карту из избранного"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserCard).where(
                and_(UserCard.id == user_card_id, UserCard.user_id == user_id)
            )
        )
        user_card = result.scalar_one_or_none()

        if not user_card:
            raise ValueError("Карта не найдена")

        user_card.is_favorite = not user_card.is_favorite
        await session.commit()

        return user_card.is_favorite


async def toggle_in_deck(user_card_id: int, user_id: int) -> bool:
    """Добавить/убрать карту из колоды"""
    async with AsyncSessionLocal() as session:
        # Проверяем сколько карт уже в колоде
        result = await session.execute(
            select(UserCard).where(
                and_(UserCard.user_id == user_id, UserCard.is_in_deck == True)
            )
        )
        deck_cards = result.scalars().all()

        result = await session.execute(
            select(UserCard).where(
                and_(UserCard.id == user_card_id, UserCard.user_id == user_id)
            )
        )
        user_card = result.scalar_one_or_none()

        if not user_card:
            raise ValueError("Карта не найдена")

        # Если добавляем в колоду
        if not user_card.is_in_deck:
            if len(deck_cards) >= 5:  # Максимум 5 карт в колоде
                raise ValueError("В колоде может быть только 5 карт")

        user_card.is_in_deck = not user_card.is_in_deck
        await session.commit()

        return user_card.is_in_deck
