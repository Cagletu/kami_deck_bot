# database/crud.py
import random
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Optional, Tuple

from database.models.user import User
from database.models.card import Card
from database.models.user_card import UserCard
from database.models.pack_opening import PackOpening
from database.models.expedition import Expedition, ExpeditionType, ExpeditionStatus
from database.models.daily_task import DailyTask, TaskType
from database.base import AsyncSessionLocal
from game.pack_system import PACK_SETTINGS
import logging

logger = logging.getLogger(__name__)

# ===== ПОЛЬЗОВАТЕЛИ =====

async def get_user_or_create(
    session: AsyncSession,
    telegram_id: int,
    username: str = None,
    first_name: str = None,
    last_name: str = None
) -> User:
    
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.last_active = datetime.now()
            return user

        new_user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name or "Игрок",
            last_name=last_name,
            last_active=datetime.now(),
            coins=500,  # Стартовые монеты
            dust=0,
            level=1
        )
        logger.info(f"Created new user: tg_id={telegram_id}")

        session.add(new_user)
        await session.flush()

        # Даем стартовые карты новому игроку
        await give_starting_cards(new_user.id, session)

        return new_user

async def give_starting_cards(user_id: int, session: AsyncSession):
    """Выдать стартовые карты новому игроку"""
    # Берем 3 случайные карты E ранга
    result = await session.execute(
        select(Card).where(Card.rarity == 'E').order_by(func.random()).limit(3)
    )
    cards = result.scalars().all()

    for card in cards:
        user_card = UserCard(
            user_id=user_id,
            card_id=card.id,
            level=1,
            current_power=card.base_power,
            current_health=card.base_health,
            current_attack=card.base_attack,
            current_defense=card.base_defense
        )
        session.add(user_card)

    await session.commit()

    # Обновляем счетчик карт
    await update_user_collection_size(user_id, session)

async def update_user_collection_size(user_id: int, session: AsyncSession = None):
    """Обновить счетчик открытых карт"""
    if not session:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count()).select_from(UserCard).where(UserCard.user_id == user_id)
            )
            count = result.scalar()

            await session.execute(
                User.__table__.update()
                .where(User.id == user_id)
                .values(cards_opened=count)
            )
            await session.commit()
    else:
        result = await session.execute(
            select(func.count()).select_from(UserCard).where(UserCard.user_id == user_id)
        )
        count = result.scalar()

        await session.execute(
            User.__table__.update()
            .where(User.id == user_id)
            .values(cards_opened=count)
        )

# ===== КОЛЛЕКЦИЯ =====

async def get_user_collection(
    user_id: int,
    page: int = 1,
    page_size: int = 10,
    rarity_filter: str = None
) -> Tuple[List[Tuple[UserCard, Card]], int, int]:
    """Получить коллекцию пользователя с пагинацией"""
    async with AsyncSessionLocal() as session:
        query = (
            select(UserCard, Card)
            .join(Card, UserCard.card_id == Card.id)
            .where(UserCard.user_id == user_id)
        )

        if rarity_filter:
            query = query.where(Card.rarity == rarity_filter.upper())

        count_query = select(func.count()).select_from(query.subquery())
        total = await session.scalar(count_query)

        query = query.order_by(
            UserCard.obtained_at.desc(),
            Card.rarity.desc()
        ).offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(query)
        items = result.all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return items, total, total_pages

async def get_collection_stats(user_id: int) -> dict:
    """Получить статистику коллекции по редкостям"""
    async with AsyncSessionLocal() as session:
        # Группировка по редкости
        result = await session.execute(
            select(
                Card.rarity,
                func.count(UserCard.id)
            )
            .join(UserCard, Card.id == UserCard.card_id)
            .where(UserCard.user_id == user_id)
            .group_by(Card.rarity)
        )

        stats = {rarity: count for rarity, count in result.all()}

        # Добавляем нули для отсутствующих редкостей
        for rarity in ['SSS', 'ASS', 'S', 'A', 'B', 'C', 'D', 'E']:
            if rarity not in stats:
                stats[rarity] = 0

        return stats

# ===== ОТКРЫТИЕ ПАЧЕК =====

async def open_pack(
    user_id: int,
    pack_type: str = "common",
    session: AsyncSession = None
) -> Tuple[List[Card], PackOpening]:
    """Открыть пачку карт с pity-системой"""
    if not session:
        async with AsyncSessionLocal() as session:
            return await _open_pack_transaction(user_id, pack_type, session)
    else:
        return await _open_pack_transaction(user_id, pack_type, session)

async def _open_pack_transaction(user_id: int, pack_type: str, session: AsyncSession):
    settings = PACK_SETTINGS.get(pack_type)
    if not settings:
        raise ValueError("Неизвестный тип пака")

    pity_a_max = settings.get("pity_a", 10)
    pity_s_max = settings.get("pity_s", 50)

    user = await session.get(User, user_id)
    if user.coins < settings["price"]:
        raise ValueError("Недостаточно монет")
    user.coins -= settings["price"]

    last_open = await session.execute(
        select(PackOpening)
        .where(PackOpening.user_id == user_id)
        .order_by(PackOpening.opened_at.desc())
        .limit(1)
    )
    last_open = last_open.scalar_one_or_none()

    pity_a = (last_open.packs_since_last_a or 0) + 1 if last_open else 0
    pity_s = (last_open.packs_since_last_s or 0) + 1 if last_open else 0

    cards = []
    rarities = []
    guaranteed_rarity = None

    # Временно храним ID карт, которые будем добавлять
    new_card_ids = []

    for _ in range(settings["cards_count"]):
        # Pity
        if pity_a >= pity_a_max:
            rarity = "A"
            guaranteed_rarity = "A"
            pity_a = 0
        elif pity_s >= pity_s_max:
            rarity = "S"
            guaranteed_rarity = "S"
            pity_s = 0
        else:
            rarity = random.choices(
                list(settings["rarity_weights"].keys()),
                weights=list(settings["rarity_weights"].values())
            )[0]

        result = await session.execute(
            select(Card)
            .where(Card.rarity == rarity)
            .order_by(func.random())
            .limit(1)
        )
        card = result.scalar_one_or_none()
        if not card:
            continue  # безопасно пропустить

        cards.append(card)
        rarities.append(rarity)
        new_card_ids.append(card.id)

        # 🔥 Увеличиваем счётчик открытых карт
        user.cards_opened += 1

        # обновляем pity
        if rarity == "A":
            pity_a = 0
        if rarity in ["S", "ASS", "SSS"]:
            pity_s = 0
        else:
            pity_a += 1
            pity_s += 1

    pack_open = PackOpening(
        user_id=user_id,
        pack_type=pack_type,
        pack_price=settings["price"],
        card_ids=[c.id for c in cards],
        rarities=rarities,
        packs_since_last_a=pity_a,
        packs_since_last_s=pity_s,
        guaranteed_rarity=guaranteed_rarity
    )
    session.add(pack_open)
    await session.commit()

    return cards, pack_open, new_card_ids

# ===== ЭКСПЕДИЦИИ =====

async def start_expedition(
    user_id: int,
    expedition_type: ExpeditionType,
    card_ids: List[int]
) -> Expedition:
    """Начать экспедицию"""
    async with AsyncSessionLocal() as session:
        # Проверяем слоты
        user = await session.get(User, user_id)

        active_expeditions = await session.execute(
            select(Expedition)
            .where(
                and_(
                    Expedition.user_id == user_id,
                    Expedition.status == "ACTIVE"
                )
            )
        )
        active_count = len(active_expeditions.scalars().all())

        if active_count >= user.expeditions_slots:
            raise ValueError("Нет свободных слотов для экспедиции")

        # Настройки длительности
        duration_map = {
            ExpeditionType.SHORT: 1, #30,
            ExpeditionType.MEDIUM: 2, #120,
            ExpeditionType.LONG: 3, #360
        }

        duration = duration_map[expedition_type]

        # Проверяем бонус за одно аниме
        cards = await session.execute(
            select(Card).where(Card.id.in_(card_ids))
        )
        cards_list = cards.scalars().all()

        anime_names = set(c.anime_name for c in cards_list)
        anime_bonus = len(anime_names) == 1

        # Рассчитываем награды
        base_coins = duration // 5  # 30 мин = 6 монет, 2ч = 24 монеты, 6ч = 72 монеты
        base_dust = duration // 30   # 30 мин = 1 пыль, 2ч = 4 пыли, 6ч = 12 пыли

        if anime_bonus:
            base_coins = int(base_coins * 1.5)
            base_dust = int(base_dust * 1.5)

        # Шанс на карту
        card_chance = min(duration // 60, 100)  # 30 мин = 50%, 2ч = 100%, 6ч = 100%

        expedition = Expedition(
            user_id=user_id,
            name=f"Экспедиция {expedition_type.value}",
            expedition_type=expedition_type.value if hasattr(expedition_type, "value") else expedition_type,
            duration_minutes=duration,
            card_ids=card_ids,
            reward_coins=base_coins,
            reward_dust=base_dust,
            reward_card_rarity="E" if duration <= 30 else "D",
            reward_card_chance=card_chance,
            anime_bonus=anime_bonus,
            ends_at=datetime.now() + timedelta(minutes=duration),
            status="ACTIVE"
        )

        session.add(expedition)

        # Помечаем карты как в экспедиции
        await session.execute(
            UserCard.__table__.update()
            .where(UserCard.id.in_(card_ids))
            .values(
                is_in_expedition=True,
                expedition_end_time=expedition.ends_at
            )
        )

        user.total_expeditions += 1
        await session.commit()
        await session.refresh(expedition)

        return expedition

async def claim_expedition(expedition_id: int) -> dict:
    """Забрать награду экспедиции"""
    async with AsyncSessionLocal() as session:
        expedition = await session.get(Expedition, expedition_id)

        if expedition.status != "COMPLETED":
            if expedition.ends_at > datetime.now():
                raise ValueError("Экспедиция еще не завершена")
            expedition.status = "COMPLETED"

        user = await session.get(User, expedition.user_id)

        # Начисляем награды
        user.coins += expedition.reward_coins
        user.dust += expedition.reward_dust

        rewards = {
            "coins": expedition.reward_coins,
            "dust": expedition.reward_dust,
            "card": None
        }

        # Проверяем шанс на карту
        if expedition.reward_card_rarity and random.randint(1, 100) <= expedition.reward_card_chance:
            result = await session.execute(
                select(Card)
                .where(Card.rarity == expedition.reward_card_rarity)
                .order_by(func.random())
                .limit(1)
            )
            card = result.scalar_one_or_none()

            if card:
                user_card = UserCard(
                    user_id=user.id,
                    card_id=card.id,
                    level=1,
                    source="expedition"
                )
                session.add(user_card)
                rewards["card"] = card

        # Освобождаем карты
        await session.execute(
            UserCard.__table__.update()
            .where(UserCard.id.in_(expedition.card_ids))
            .values(
                is_in_expedition=False,
                expedition_end_time=None
            )
        )

        expedition.collected = True
        expedition.completed_at = datetime.now()

        await session.commit()

        return rewards


async def get_user_cards_paginated(
    session,
    user_id: int,
    page: int = 0,
    page_size: int = 6,
    rarity: str | None = None,
    search: str | None = None,
):
    query = (
        select(UserCard)
        .join(Card, UserCard.card_id == Card.id)
        .where(UserCard.user_id == user_id)
        .options(selectinload(UserCard.card))
    )

    if rarity:
        query = query.where(Card.rarity == rarity)

    if search:
        query = query.where(
            Card.card_name.ilike(f"%{search}%")
        )

    query = query.offset(page * page_size).limit(page_size + 1)

    result = await session.execute(query)
    cards = result.scalars().all()

    has_next = len(cards) > page_size
    return cards[:page_size], has_next


async def claim_daily_reward(user_id: int, session: AsyncSession) -> dict:
    """Получить ежедневную награду"""
    user = await session.get(User, user_id)

    if user.last_daily_tasks and user.last_daily_tasks.date() == datetime.now().date():
        raise ValueError("Ежедневная награда уже получена")

    reward_coins = 100
    reward_dust = 10

    user.coins += reward_coins
    user.dust += reward_dust
    user.last_daily_tasks = datetime.now()

    await session.commit()

    return {
        "coins": reward_coins,
        "dust": reward_dust,
        "total_coins": user.coins,
        "total_dust": user.dust
    }


async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    """Получить пользователя по telegram_id"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def get_user_cards_count(user_id: int, rarity: str = None) -> int:
    """Получить количество карт пользователя"""
    async with AsyncSessionLocal() as session:
        query = select(func.count()).select_from(UserCard).where(UserCard.user_id == user_id)

        if rarity:
            query = (
                select(func.count())
                .select_from(UserCard)
                .join(Card, UserCard.card_id == Card.id)
                .where(UserCard.user_id == user_id, Card.rarity == rarity)
            )

        return await session.scalar(query)


async def sync_user_deck(session, user_id: int):
    """
    Синхронизирует JSON selected_deck в users
    на основе флагов is_in_deck в user_cards
    """
    result = await session.execute(
        select(UserCard.id).where(
            UserCard.user_id == user_id,
            UserCard.is_in_deck == True
        )
    )

    deck_ids = [row[0] for row in result.all()]

    user = await session.get(User, user_id)
    user.selected_deck = deck_ids

    return deck_ids
