import random
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.user import User
from database.models.card import Card
from database.models.user_card import UserCard
from database.models.expedition import Expedition, ExpeditionType, ExpeditionStatus
from database.base import AsyncSessionLocal


class ExpeditionManager:

    @staticmethod
    async def get_available_cards(session: AsyncSession, user_id: int) -> List[Tuple[UserCard, Card]]:
        """Получить карты доступные для экспедиции"""
        result = await session.execute(
            select(UserCard, Card)
            .join(Card, UserCard.card_id == Card.id)
            .where(
                and_(
                    UserCard.user_id == user_id,
                    not UserCard.is_in_expedition,
                    not UserCard.is_in_deck
                )
            )
            .order_by(Card.rarity.desc(), UserCard.level.desc())
            .limit(50)
        )
        return result.all()

    @staticmethod
    async def get_active_expeditions(session: AsyncSession, user_id: int) -> Tuple[List[Expedition], List[Expedition]]:
        """Получить активные и завершенные экспедиции"""
        # Проверяем завершенные
        now = datetime.now()
        await session.execute(
            Expedition.__table__.update()
            .where(
                and_(
                    Expedition.user_id == user_id,
                    Expedition.status == ExpeditionStatus.ACTIVE,
                    Expedition.ends_at <= now
                )
            )
            .values(status=ExpeditionStatus.COMPLETED)
        )
        await session.commit()

        # Получаем активные
        result = await session.execute(
            select(Expedition)
            .where(
                and_(
                    Expedition.user_id == user_id,
                    Expedition.status == ExpeditionStatus.ACTIVE
                )
            )
            .order_by(Expedition.ends_at)
        )
        active = result.scalars().all()

        # Получаем незабранные
        result = await session.execute(
            select(Expedition)
            .where(
                and_(
                    Expedition.user_id == user_id,
                    Expedition.status == ExpeditionStatus.COMPLETED,
                    not Expedition.collected
                )
            )
        )
        uncollected = result.scalars().all()

        return active, uncollected

    @staticmethod
    async def calculate_rewards(
        session: AsyncSession,
        card_ids: List[int],
        duration_minutes: int
    ) -> dict:
        """Рассчитать награды за экспедицию"""
        # Базовая награда за 1 карту (исправить при проде на // вместо * оба)
        base_coins = duration_minutes * 5  # 30м=6, 2ч=24, 6ч=72
        base_dust = duration_minutes * 30   # 30м=1, 2ч=4, 6ч=12

        # Множитель за количество карт (1-3x)
        card_multiplier = len(card_ids)

        # Проверяем бонус за одно аниме
        cards_result = await session.execute(
            select(Card)
            .join(UserCard, UserCard.card_id == Card.id)
            .where(UserCard.id.in_(card_ids))
        )
        cards = cards_result.scalars().all()
        anime_set = set(c.anime_name for c in cards)
        anime_bonus = len(anime_set) == 1

        if anime_bonus:
            card_multiplier = int(card_multiplier * 1.5)

        # Шанс на карту
        card_chance = min(duration_minutes // 60 * len(card_ids), 100)

        # Редкость карты
        if duration_minutes <= 30:
            card_rarity = "E"
        elif duration_minutes <= 120:
            card_rarity = "D"
        else:
            card_rarity = "C"

        return {
            "coins": base_coins * card_multiplier,
            "dust": base_dust * card_multiplier,
            "card_rarity": card_rarity,
            "card_chance": card_chance,
            "anime_bonus": anime_bonus,
            "multiplier": card_multiplier
        }

    @staticmethod
    async def start_expedition(
        session: AsyncSession,
        user_id: int,
        card_ids: List[int],
        duration_type: str
    ) -> Expedition:
        """Начать экспедицию"""
        # Проверка количества карт
        if len(card_ids) < 1 or len(card_ids) > 3:
            raise ValueError("Можно отправить от 1 до 3 карт")

        # Длительность (исправить при проде)
        duration_map = {
            "short": 1, # 30,
            "medium": 2, # 120,
            "long": 3 # 360
        }
        duration = duration_map[duration_type]

        # Расчет наград
        rewards = await ExpeditionManager.calculate_rewards(card_ids, duration)

        # Создание экспедиции
        # Проверяем слоты
        user = await session.get(User, user_id)
        active, _ = await ExpeditionManager.get_active_expeditions(user_id)

        if len(active) >= user.expeditions_slots:
            raise ValueError("Нет свободных слотов для экспедиции")

        cards_check = await session.execute(
            select(UserCard)
            .where(UserCard.id.in_(card_ids))
            .where(UserCard.user_id == user_id)
            .where(UserCard.is_in_expedition == False)
        )

        valid_cards = cards_check.scalars().all()

        if len(valid_cards) != len(card_ids):
            raise ValueError("Одна из карт уже используется")


        expedition = Expedition(
            user_id=user_id,
            name=f"Экспедиция {duration}мин ({len(card_ids)} карт)",
            expedition_type=ExpeditionType(duration_type),
            duration_minutes=duration,
            card_ids=card_ids,
            reward_coins=rewards["coins"],
            reward_dust=rewards["dust"],
            reward_card_rarity=rewards["card_rarity"],
            reward_card_chance=rewards["card_chance"],
            anime_bonus=rewards["anime_bonus"],
            rarity_bonus=rewards["multiplier"],
            ends_at=datetime.now() + timedelta(minutes=duration),
            status=ExpeditionStatus.ACTIVE,
            collected=False
        )

        session.add(expedition)

        # Помечаем карты
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

    @staticmethod
    async def claim_expedition(session: AsyncSession, expedition_id: int) -> dict:
        """Забрать награду одной экспедиции""":
        expedition = await session.get(Expedition, expedition_id)

        if expedition.collected:
            raise ValueError("Награда уже получена")

        if expedition.status != ExpeditionStatus.COMPLETED:
            if expedition.ends_at > datetime.now():
                raise ValueError("Экспедиция еще не завершена")
            expedition.status = ExpeditionStatus.COMPLETED

        user = await session.get(User, expedition.user_id)

        # Начисляем награды
        user.coins += expedition.reward_coins
        user.dust += expedition.reward_dust

        rewards = {
            "coins": expedition.reward_coins,
            "dust": expedition.reward_dust,
            "card": None
        }

        # Шанс на карту
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

                # Обновляем счетчик карт
                user.cards_opened += 1

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

    @staticmethod
    async def claim_all_expeditions(user_id: int) -> dict:
        """Забрать награды всех завершенных экспедиций"""
        _, uncollected = await ExpeditionManager.get_active_expeditions(user_id)

        total_coins = 0
        total_dust = 0
        cards_won = []

        for expedition in uncollected:
            rewards = await ExpeditionManager.claim_expedition(expedition.id)
            total_coins += rewards["coins"]
            total_dust += rewards["dust"]
            if rewards["card"]:
                cards_won.append(rewards["card"])

        return {
            "coins": total_coins,
            "dust": total_dust,
            "cards": cards_won,
            "count": len(uncollected)
        }