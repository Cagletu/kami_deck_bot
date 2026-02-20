import random
from datetime import datetime, timedelta
import math
from typing import List, Tuple, Optional
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.user import User
from database.models.card import Card
from database.models.user_card import UserCard
from database.models.expedition import Expedition, ExpeditionType, ExpeditionStatus
from database.base import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)


class ExpeditionManager:

    @staticmethod
    async def get_available_cards(session: AsyncSession,
                                  user_id: int) -> List[Tuple[UserCard, Card]]:
        """Получить карты доступные для экспедиции"""

        # Приоритет редкости: SSS > ASS > S > A > B > C > D > E
        rarity_order = {
            'SSS': 0,
            'ASS': 1,
            'S': 2,
            'A': 3,
            'B': 4,
            'C': 5,
            'D': 6,
            'E': 7
        }

        result = await session.execute(
            select(UserCard,
                   Card).join(Card, UserCard.card_id == Card.id).where(
                       UserCard.user_id == user_id,
                       UserCard.is_in_expedition == False,  # Не в экспедиции
                       UserCard.is_in_deck == False  # Не в колоде
                   ).limit(50))

        cards = result.all()
        logger.info(f"Доступных карт после фильтрации: {len(cards)}")

        # сортировка по рангу → по уровню
        cards.sort(
            key=lambda x: (rarity_order.get(x[1].rarity, 999), -x[0].level))

        return cards

    @staticmethod
    async def get_active_expeditions(
            session: AsyncSession,
            user_id: int) -> Tuple[List[Expedition], List[Expedition]]:
        """Получить активные и завершенные экспедиции"""
        logger.info(f"🔍 get_active_expeditions для user_id={user_id}")

        # Проверяем завершенные
        now = datetime.now()
        result = await session.execute(Expedition.__table__.update().where(
            and_(Expedition.user_id == user_id,
                 Expedition.status == ExpeditionStatus.ACTIVE,
                 Expedition.ends_at
                 <= now)).values(status=ExpeditionStatus.COMPLETED).returning(
                     Expedition.id))
        updated = result.rowcount
        if updated > 0:
            logger.info(f"✅ Завершено экспедиций: {updated}")

        # Получаем активные
        result = await session.execute(
            select(Expedition).where(
                and_(Expedition.user_id == user_id,
                     Expedition.status == ExpeditionStatus.ACTIVE)).order_by(
                         Expedition.ends_at))
        active = result.scalars().all()
        logger.info(f"📊 Активных экспедиций: {len(active)}")

        # Получаем незабранные
        result = await session.execute(
            select(Expedition).where(
                and_(Expedition.user_id == user_id,
                     Expedition.status == ExpeditionStatus.COMPLETED,
                     Expedition.collected == False)))
        uncollected = result.scalars().all()
        logger.info(f"📊 Незабранных экспедиций: {len(uncollected)}")

        return active, uncollected

    @staticmethod
    async def get_uncollected_expeditions_info(session, user_id):

        now = datetime.now()

        uncollected = await session.execute(
            select(Expedition)
            .where(
                Expedition.user_id == user_id,
                Expedition.ends_at <= now,
                Expedition.collected == False
            )
        )

        return uncollected.scalars().all()

    @staticmethod
    async def calculate_rewards(
        session: AsyncSession,
        card_ids: List[int],
        duration_minutes: int
    ) -> dict:
        """Рассчитать награды за экспедицию"""
        base_coins = duration_minutes // 5
        base_dust = duration_minutes // 30

        # Множитель за количество карт (1x, 2x, 3x)
        card_multiplier = len(card_ids)

        # Проверяем бонус за одно аниме (только если карт >= 2)
        anime_bonus = False
        if len(card_ids) >= 2:
            cards_result = await session.execute(
                select(Card)
                .join(UserCard, UserCard.card_id == Card.id)
                .where(UserCard.id.in_(card_ids))
            )
            cards = cards_result.scalars().all()
            anime_set = set(c.anime_name for c in cards)
            anime_bonus = len(anime_set) == 1

        # Применяем бонус только если карт >= 2 и они из одного аниме
        if anime_bonus:
            card_multiplier = int(card_multiplier * 1.5)

        # Шанс на карту
        card_chance = min(
            (duration_minutes // 60) * len(card_ids) * 20,
            100
        )

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
    async def start_expedition(session: AsyncSession, user_id: int,
                               card_ids: List[int],
                               duration_type: str) -> Expedition:
        """Начать экспедицию"""
        logger.info(
            f"🚀 start_expedition: user_id={user_id}, card_ids={card_ids}, duration={duration_type}"
        )
        # Проверка количества карт
        if len(card_ids) < 1 or len(card_ids) > 3:
            raise ValueError("Можно отправить от 1 до 3 карт")

        # Длительность (исправить при проде)
        duration_map = {
            "short": 30,  # 30,
            "medium": 120,  # 120,
            "long": 360  # 360
        }
        duration = duration_map[duration_type]

        # Расчет наград
        rewards = await ExpeditionManager.calculate_rewards(
            session, card_ids, duration)

        # Создание экспедиции
        # Проверяем слоты
        user = await session.get(User, user_id)
        if not user:
            logger.error(f"❌ Пользователь {user_id} не найден")
            raise ValueError("Пользователь не найден")
        active, _ = await ExpeditionManager.get_active_expeditions(
            session, user_id)

        if len(active) >= user.expeditions_slots:
            logger.error(
                f"❌ Нет свободных слотов: {len(active)} >= {user.expeditions_slots}"
            )
            raise ValueError("Нет свободных слотов для экспедиции")

        cards_check = await session.execute(
            select(UserCard).where(UserCard.id.in_(card_ids)).where(
                UserCard.user_id == user_id).where(
                    UserCard.is_in_expedition == False))

        valid_cards = cards_check.scalars().all()
        logger.info(
            f"✅ Доступных карт из запрошенных: {len(valid_cards)} из {len(card_ids)}"
        )

        if len(valid_cards) != len(card_ids):
            # Найдем какие карты недоступны
            for card_id in card_ids:
                card_check = await session.execute(
                    select(UserCard).where(UserCard.id == card_id))
                card = card_check.scalar_one_or_none()
                if card:
                    logger.error(
                        f"❌ Карта {card_id}: is_in_expedition={card.is_in_expedition}, is_in_deck={card.is_in_deck}"
                    )
                else:
                    logger.error(f"❌ Карта {card_id} не найдена")
            raise ValueError(
                "Некоторые карты уже используются в экспедиции или колоде")

        # Округляем время начала до текущего момента
        now = datetime.now()
        ends_at = now + timedelta(minutes=duration)

        # Убеждаемся что ends_at точно в будущем
        if ends_at <= now:
            ends_at = now + timedelta(seconds=1)

        # Создаем экспедицию
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
            ends_at=ends_at,
            status=ExpeditionStatus.ACTIVE,
            collected=False)

        session.add(expedition)
        logger.info("➕ Экспедиция создана, ожидает flush")

        # Пробуем flush чтобы увидеть ошибки до commit
        try:
            await session.flush()
            logger.info(f"✅ Flush успешен, expedition.id = {expedition.id}")
        except Exception as e:
            logger.error(f"❌ Ошибка при flush: {e}")
            raise

        # Помечаем карты
        result = await session.execute(UserCard.__table__.update().where(
            UserCard.id.in_(card_ids)).values(
                is_in_expedition=True, expedition_end_time=expedition.ends_at))
        logger.info(f"🔄 Обновлено карт: {result.rowcount}")

        user.total_expeditions += 1

        logger.info(
            f"✅ Экспедиция {expedition.id} успешно создана и готова к коммиту")

        return expedition

    @staticmethod
    async def claim_expedition(session: AsyncSession,
                               expedition_id: int) -> dict:
        """Забрать награду одной экспедиции"""
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
            "card": None,
            "card_data": None  # для показа изображения
        }

        # Шанс на карту
        if expedition.reward_card_rarity and random.randint(
                1, 100) <= expedition.reward_card_chance:
            result = await session.execute(
                select(Card).where(
                    Card.rarity == expedition.reward_card_rarity).order_by(
                        func.random()).limit(1))
            card = result.scalar_one_or_none()

            if card:
                user_card = UserCard(user_id=user.id,
                                     card_id=card.id,
                                     level=1,
                                     source="expedition")
                session.add(user_card)
                rewards["card"] = card
                rewards["card_data"] = {
                    "id": card.id,
                    "name": card.card_name,
                    "rarity": card.rarity,
                    "url": card.original_url
                }

                # Обновляем счетчик карт
                user.cards_opened += 1

        # Освобождаем карты
        await session.execute(UserCard.__table__.update().where(
            UserCard.id.in_(expedition.card_ids)).values(
                is_in_expedition=False, expedition_end_time=None))

        expedition.collected = True
        expedition.completed_at = datetime.now()

        return rewards

    @staticmethod
    async def claim_all_expeditions(session: AsyncSession,
                                    user_id: int) -> dict:
        """Забрать награды всех завершенных экспедиций"""
        _, uncollected = await ExpeditionManager.get_active_expeditions(
            session, user_id)

        total_coins = 0
        total_dust = 0
        cards_won = []

        for expedition in uncollected:
            rewards = await ExpeditionManager.claim_expedition(
                session, expedition.id)
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
