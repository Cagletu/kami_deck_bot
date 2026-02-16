from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from database.models.user_card import UserCard
from database.models.card import Card
from game.constants import DUST_PER_RARITY

# Сколько пыли давать за дубликат (50% от стоимости прокачки)
DUST_FOR_DUPLICATE = {
    'E': 75,
    'D': 100,
    'C': 150,
    'B': 200,
    'A': 333,
    'S': 777,
    'ASS': 1000,
    'SSS': 1500
}

async def check_for_duplicate(
    session: AsyncSession,
    user_id: int,
    card_id: int
) -> dict:
    """Проверить, является ли карта дубликатом (ДО добавления в БД)"""

    # Получаем информацию о карте
    card_result = await session.execute(
        select(Card).where(Card.id == card_id)
    )
    card = card_result.scalar_one_or_none()

    if not card:
        return {"is_duplicate": False, "dust_earned": 0, "card": None}

    # Проверяем, есть ли у пользователя такая карта
    existing = await session.execute(
        select(UserCard)
        .where(
            and_(
                UserCard.user_id == user_id,
                UserCard.card_id == card_id
            )
        )
    )
    existing_card = existing.scalar_one_or_none()

    # Если карта уже есть - это дубликат
    if existing_card:
        dust_earned = DUST_FOR_DUPLICATE.get(card.rarity, 75)
        return {
            "is_duplicate": True,
            "dust_earned": dust_earned,
            "card": card,
            "existing_card_id": existing_card.id
        }

    # Если карты нет - это новая карта
    return {
        "is_duplicate": False,
        "dust_earned": 0,
        "card": card
    }


async def process_duplicate(
    session: AsyncSession,
    user_id: int,
    card_id: int,
    dust_earned: int
) -> None:
    """Обработать дубликат (начислить пыль, НЕ добавлять карту)"""
    from database.models.user import User

    user = await session.get(User, user_id)
    if user:
        user.dust += dust_earned
        user.total_duplicates_dusted += 1
    