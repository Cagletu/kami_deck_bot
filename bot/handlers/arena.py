from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select, and_, func
import json
import random
import uuid
from datetime import datetime
import logging

from database.base import AsyncSessionLocal
from database.crud import get_user_or_create
from database.models.user import User
from database.models.user_card import UserCard
from database.models.card import Card
from database.models.arena_battle import ArenaBattle as DBArenaBattle
from game.arena_battle_system import ArenaBattle, BattleCard
from services.redis_client import battle_storage


router = Router()
logger = logging.getLogger(__name__)

# URL для WebApp (ваш Railway домен)
WEBAPP_URL = "https://kamideckbot-production.up.railway.app/arena.html"


async def get_user_deck(user_id: int) -> list:
    """Получает колоду пользователя (до 5 карт)"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserCard, Card)
            .join(Card, UserCard.card_id == Card.id)
            .where(and_(UserCard.user_id == user_id, UserCard.is_in_deck == True))
            .order_by(Card.rarity.desc())
            .limit(5)
        )
        return result.all()


async def generate_opponent(user_id: int) -> tuple:
    """Генерирует колоду противника"""

    async with AsyncSessionLocal() as session:

        # Ищем игроков с полной колодой (>=5 карт)
        result = await session.execute(
            select(User)
            .where(
                User.id != user_id,
                func.coalesce(func.json_array_length(User.selected_deck), 0) >= 5,
            )
            .order_by(func.random())
            .limit(1)
        )

        opponent = result.scalar_one_or_none()

        if opponent and opponent.selected_deck:

            result = await session.execute(
                select(UserCard, Card)
                .join(Card, UserCard.card_id == Card.id)
                .where(UserCard.id.in_(opponent.selected_deck))
                .limit(5)
            )

            opponent_cards = result.all()

            if len(opponent_cards) >= 5:
                logger.info(f"Found real opponent: {opponent.id}")
                return opponent_cards, opponent.id

        logger.info("No real opponent found, generating test deck")
        return await generate_test_deck(), None


async def generate_test_deck() -> list:
    """Генерирует тестовую колоду"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Card).order_by(func.random()).limit(5))
        cards = result.scalars().all()

        test_deck = []
        for i, card in enumerate(cards):
            level = random.randint(5, 20)

            # Рассчитываем характеристики на основе уровня
            power = int(card.base_power * (1 + (level - 1) * 0.06))  # +6% за уровень
            health = int(card.base_health * (1 + (level - 1) * 0.04))  # +4% за уровень
            attack = int(card.base_attack * (1 + (level - 1) * 0.07))  # +7% за уровень
            defense = int(
                card.base_defense * (1 + (level - 1) * 0.04)
            )  # +4% за уровень

            # Добавляем бонус редкости
            rarity_mult = {
                "E": 1.0,
                "D": 1.1,
                "C": 1.2,
                "B": 1.3,
                "A": 1.45,
                "S": 1.65,
                "ASS": 1.8,
                "SSS": 2.0,
            }.get(card.rarity, 1.0)

            power = int(power * rarity_mult)
            health = int(health * rarity_mult)
            attack = int(attack * rarity_mult)
            defense = int(defense * rarity_mult)

            test_deck.append(
                (
                    type(
                        "UserCard",
                        (),
                        {
                            "id": -i - 1,
                            "user_id": -1,
                            "card_id": card.id,
                            "level": level,
                            "current_power": power,
                            "current_health": health,
                            "current_attack": attack,
                            "current_defense": defense,
                            "is_in_deck": True,
                        },
                    ),
                    card,
                )
            )

        return test_deck


def prepare_battle_cards(cards_data: list, is_user: bool = True) -> list:
    """Подготавливает карты для боя"""
    battle_cards = []
    for i, (user_card, card) in enumerate(cards_data[:5]):
        battle_card = BattleCard(
            id=user_card.id if is_user else -user_card.id,
            user_card_id=user_card.id,
            name=card.card_name,
            rarity=card.rarity,
            anime=card.anime_name or "Unknown",
            power=user_card.current_power,
            health=user_card.current_health,
            max_health=user_card.current_health,
            attack=user_card.current_attack,
            defense=user_card.current_defense,
            level=user_card.level,
            image_url=card.original_url,
            position=i,
        )
        battle_cards.append(battle_card)
    return battle_cards


@router.message(Command("arena"))
async def cmd_arena(message: types.Message, user_id: int = None):
    """Вход на арену"""
    # Определяем какой ID использовать
    if user_id:
        tg_id = user_id
    else:
        tg_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, tg_id)

        logger.info(f"Arena user: tg_id={tg_id}, db_id={user.id}")

        # Получаем колоду пользователя
        user_deck = await get_user_deck(user.id)

        if len(user_deck) < 5:
            await message.answer(
                "❌ <b>Недостаточно карт в колоде!</b>\n\n"
                f"Сейчас в колоде: {len(user_deck)}/5 карт\n\n"
                "Используйте /collection чтобы добавить карты в колоду",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🃏 К коллекции",
                                callback_data="collection_by_rarity",
                            )
                        ]
                    ]
                ),
            )
            return

        # Генерируем противника
        opponent_deck, opponent_id = await generate_opponent(user.id)

        # Создаем уникальный ID для боя
        battle_id = str(uuid.uuid4())

        # Подготавливаем карты
        user_battle_cards = prepare_battle_cards(user_deck, is_user=True)
        opponent_battle_cards = prepare_battle_cards(opponent_deck, is_user=False)

        # Создаем бой
        battle = ArenaBattle(user_battle_cards, opponent_battle_cards)

        battle_data = {
            "user_id": message.from_user.id,
            "opponent_id": opponent_id,
            "player_cards": [card.to_dict() for card in user_battle_cards],
            "enemy_cards": [card.to_dict() for card in opponent_battle_cards],
            "turn": 0,
            "winner": None,
            "created_at": datetime.now().isoformat(),
        }

        logger.info(
            f"Saving battle {battle_id} to Redis: {len(battle_data['player_cards'])} player cards, {len(battle_data['enemy_cards'])} enemy cards"
        )
        await battle_storage.save_battle(battle_id, battle_data)

        # ✅ ИСПРАВЛЕНО: Используем InlineKeyboardMarkup с web_app
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚔️ НАЧАТЬ БИТВУ",
                        web_app=WebAppInfo(url=f"{WEBAPP_URL}?battle_id={battle_id}"),
                    )
                ],
                [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")],
            ]
        )

        # Информация о битве
        text = f"""
<b>⚔️ АРЕНА ЖДЕТ!</b>

📊 <b>Ваша колода:</b> 5/5 карт
{'⭐ Есть синергия!' if battle.player_synergies else '🔄 Без синергии'}

👹 <b>Противник:</b> {'Реальный игрок' if opponent_id else 'Тестовая колода'}

⚡ <b>Нажмите кнопку ниже чтобы начать битву!</b>
"""

        await message.answer(text, reply_markup=keyboard)

    except Exception as e:
        logger.exception(f"Ошибка cmd_arena: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "open_arena")
async def open_arena(callback: types.CallbackQuery):
    """Обработчик кнопки открытия арены"""
    try:
        # Передаем правильный параметр
        await cmd_arena(callback.message, callback.from_user.id)
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка в open_arena: {e}")
        await callback.answer("❌ Ошибка открытия арены", show_alert=True)


@router.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    """Обрабатывает данные из WebApp"""
    try:
        # 🚨 ВАЖНО: логируем ВСЕ входящие данные
        logger.info("=" * 50)
        logger.info("🔥 ПОЛУЧЕНЫ WEBAPP DATA!")
        logger.info(f"User ID: {message.from_user.id}")
        logger.info(f"Raw data: {message.web_app_data.data}")

        data = json.loads(message.web_app_data.data)
        logger.info(f"Parsed data: {data}")

        action = data.get("action")
        battle_id = data.get("battle_id")
        result = data.get("result")
        rewards = data.get("rewards", {})

        logger.info(f"Action: {action}")
        logger.info(f"Battle ID: {battle_id}")
        logger.info(f"Result: {result}")
        logger.info(f"Rewards: {rewards}")

        # ===== ТЕСТОВЫЙ ЭНДПОИНТ =====
        if action == "test":
            logger.info("✅ Test data received!")
            await message.answer("✅ Тестовые данные получены!")
            return

        # ===== ОБРАБОТКА РЕЗУЛЬТАТА БИТВЫ =====
        if action == "battle_result":
            logger.info(f"🎯 Processing battle result: {result}")

            async with AsyncSessionLocal() as session:
                user = await get_user_or_create(session, message.from_user.id)
                logger.info(f"👤 User found: ID={user.id}, coins={user.coins}, dust={user.dust}, rating={user.arena_rating}")

                # Сохраняем старые значения для отчета
                old_stats = {
                    "wins": user.arena_wins,
                    "losses": user.arena_losses,
                    "rating": user.arena_rating,
                    "coins": user.coins,
                    "dust": user.dust,
                }

                # Получаем данные битвы из Redis
                battle_data = None
                if battle_id:
                    battle_data = await battle_storage.get_battle(battle_id)
                    if battle_data:
                        logger.info("✅ Battle data found in Redis")
                    else:
                        logger.warning(f"❌ Battle data NOT found in Redis for {battle_id}")

                # Начисляем награды
                if result == "win":
                    rating_change = rewards.get("rating", 20)
                    coins_reward = rewards.get("coins", 50)
                    dust_reward = rewards.get("dust", 50)

                    user.arena_wins += 1
                    user.arena_rating += rating_change
                    user.coins += coins_reward
                    user.dust += dust_reward

                    logger.info(f"✅ WIN: +{rating_change} rating, +{coins_reward} coins, +{dust_reward} dust")

                elif result == "lose":
                    rating_change = rewards.get("rating", -15)
                    coins_reward = rewards.get("coins", 25)
                    dust_reward = rewards.get("dust", 25)

                    user.arena_losses += 1
                    user.arena_rating = max(0, user.arena_rating + rating_change)
                    user.coins += coins_reward
                    user.dust += dust_reward

                    logger.info(f"✅ LOSE: {rating_change} rating, +{coins_reward} coins, +{dust_reward} dust")

                # Сохраняем битву в БД
                db_battle = DBArenaBattle(
                    attacker_id=user.id,
                    defender_id=battle_data.get("opponent_id") if battle_data else -1,
                    attacker_deck=[c.get("user_card_id") for c in (battle_data.get("player_cards") if battle_data else []) if c.get("user_card_id", 0) > 0],
                    defender_deck=[c.get("user_card_id") for c in (battle_data.get("enemy_cards") if battle_data else []) if c.get("user_card_id", 0) > 0],
                    rounds=battle_data.get("turn", 0) if battle_data else 0,
                    winner_id=user.id if result == "win" else None,
                    result="attacker_win" if result == "win" else "defender_win",
                    attacker_rating_change=rating_change if result == "win" else rating_change,
                    attacker_reward_coins=coins_reward,
                    attacker_reward_dust=dust_reward,
                    ended_at=datetime.now()
                )
                session.add(db_battle)

                # Сохраняем изменения в БД
                await session.commit()
                logger.info("✅ Battle saved to database")

                await session.refresh(user)
                logger.info(f"✅ User updated: wins={user.arena_wins}, rating={user.arena_rating}, coins={user.coins}")

                # Отправляем подтверждение
                await message.answer(
                    f"{'🎉' if result == 'win' else '😔'} <b>БИТВА ЗАВЕРШЕНА!</b>\n\n"
                    f"📊 Статистика:\n"
                    f"├ Побед: {old_stats['wins']} → {user.arena_wins}\n"
                    f"├ Поражений: {old_stats['losses']} → {user.arena_losses}\n"
                    f"├ Рейтинг: {old_stats['rating']} → {user.arena_rating}\n"
                    f"├ Монеты: {old_stats['coins']} → {user.coins}\n"
                    f"└ Пыль: {old_stats['dust']} → {user.dust}"
                )

                # Удаляем битву из Redis
                if battle_id:
                    await battle_storage.delete_battle(battle_id)
                    logger.info(f"✅ Battle {battle_id} deleted from Redis")

            return

        elif action == "close_arena":
            logger.info(f"👋 User {message.from_user.id} closed arena")
            return

        else:
            logger.warning(f"⚠️ Unknown action: {action}")

    except Exception as e:
        logger.exception(f"❌ Ошибка обработки WebApp данных: {e}")
        await message.answer(json.dumps({"type": "error", "message": str(e)}))
