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

async def check_and_process_duplicates(
    session: AsyncSession,
    user_id: int,
    new_card_id: int
) -> dict:
    """Проверить, есть ли у пользователя такая карта, и обработать дубликат"""

    # Получаем информацию о новой карте
    result = await session.execute(
        select(Card).where(Card.id == new_card_id)
    )
    new_card = result.scalar_one_or_none()

    if not new_card:
        return {"is_duplicate": False, "dust_earned": 0}

    # Проверяем, есть ли у пользователя такая карта
    result = await session.execute(
        select(UserCard)
        .where(
            and_(
                UserCard.user_id == user_id,
                UserCard.card_id == new_card_id
            )
        )
    )
    existing_cards = result.scalars().all()

    # Если это первая карта - не дубликат
    if len(existing_cards) == 0:
        return {"is_duplicate": False, "dust_earned": 0, "card": new_card}

    # Это дубликат - выдаем пыль
    dust_earned = DUST_FOR_DUPLICATE.get(new_card.rarity, 75)

    # Находим пользователя и начисляем пыль
    from database.models.user import User
    user = await session.get(User, user_id)
    user.dust += dust_earned
    user.total_duplicates_dusted += 1

    return {
        "is_duplicate": True,
        "dust_earned": dust_earned,
        "card": new_card,
        "duplicate_count": len(existing_cards) + 1
    }
    