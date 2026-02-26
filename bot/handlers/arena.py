#bot/handlers/arena.py
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
from game.arena_ranks import get_rank, ARENA_RANKS


router = Router()
logger = logging.getLogger(__name__)

# URL для WebApp (ваш Railway домен)
WEBAPP_URL = "https://kamideckbot-production.up.railway.app/arena.html"


def generate_init_data(user_id: int, battle_id: str) -> str:
    """
    Генерирует имитацию init_data для передачи в URL
    """
    # Создаем простую структуру данных
    data = {
        "user_id": str(user_id),
        "battle_id": battle_id,
        "timestamp": str(int(datetime.now().timestamp()))
    }

    # Кодируем в JSON и затем в base64 для безопасной передачи в URL
    import base64
    json_str = json.dumps(data)
    encoded = base64.b64encode(json_str.encode()).decode()

    return encoded


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


async def generate_opponent(user_id: int, user_rating: int) -> tuple:
    """Генерирует колоду противника с учетом рейтинга"""
    async with AsyncSessionLocal() as session:
        # Пытаемся найти противника с похожим рейтингом (±200)
        rating_range_low = max(0, user_rating - 500)
        rating_range_high = user_rating + 500

        result = await session.execute(
            select(User)
            .where(
                User.id != user_id,
                User.arena_rating.between(rating_range_low, rating_range_high),
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
                logger.info(f"Found real opponent: {opponent.id} with rating {opponent.arena_rating}")
                return opponent_cards, opponent.id, opponent.arena_rating

        # Если не нашли реального противника, генерируем тестовую колоду
        # с рейтингом, близким к пользователю
        logger.info("No real opponent found, generating test deck")
        test_rating = max(500, user_rating + random.randint(-300, 300))
        return await generate_test_deck(user_rating), None, test_rating


async def generate_test_deck(user_rating: int) -> list:
    """Генерирует тестовую колоду с указанием, что она тестовая"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Card).order_by(func.random()).limit(5))
        cards = result.scalars().all()

        # Определяем силу тестовой колоды в зависимости от рейтинга
        level_base = max(5, min(30, user_rating // 150 + 5))

        test_deck = []
        for i, card in enumerate(cards):
            level = level_base + random.randint(-3, 3)

            # Рассчитываем характеристики на основе уровня
            power = int(card.base_power * (1 + (level - 1) * 0.06))
            health = int(card.base_health * (1 + (level - 1) * 0.04))
            attack = int(card.base_attack * (1 + (level - 1) * 0.07))
            defense = int(card.base_defense * (1 + (level - 1) * 0.04))

            rarity_mult = {
                "E": 1.0, "D": 1.1, "C": 1.2, "B": 1.3,
                "A": 1.45, "S": 1.65, "ASS": 1.8, "SSS": 2.0,
            }.get(card.rarity, 1.0)

            power = int(power * rarity_mult)
            health = int(health * rarity_mult)
            attack = int(attack * rarity_mult)
            defense = int(defense * rarity_mult)

            # Добавляем флаг, что это тестовая карта
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
                            "is_test_card": True,  # Флаг тестовой карты
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

        # Получаем ранг игрока
        from game.arena_ranks import get_rank_display, get_next_rank_progress

        rank_display = get_rank_display(user.arena_rating)
        needed, total, progress = get_next_rank_progress(user.arena_rating)

        progress_bar = "█" * int(progress // 10) + "░" * (10 - int(progress // 10))

        # Генерируем противника с учетом рейтинга
        opponent_deck, opponent_id, opponent_rating = await generate_opponent(user.id, user.arena_rating)

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
            "player_rating": user.arena_rating,
            "opponent_rating": opponent_rating,
        }

        logger.info(
            f"Saving battle {battle_id} to Redis: {len(battle_data['player_cards'])} player cards, {len(battle_data['enemy_cards'])} enemy cards"
        )
        await battle_storage.save_battle(battle_id, battle_data)

        # Генерируем init_data для передачи в URL
        init_data = generate_init_data(tg_id, battle_id)

        # Создаем кнопку с WebApp и передаем данные через URL
        webapp_url = f"{WEBAPP_URL}?battle_id={battle_id}&init_data={init_data}"

        # ✅ ИСПРАВЛЕНО: Используем InlineKeyboardMarkup с web_app
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚔️ НАЧАТЬ БИТВУ",
                        web_app=WebAppInfo(url=webapp_url),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏆 ТОП ИГРОКОВ",
                        callback_data="arena_top"
                    )
                ],
                [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")],
            ]
        )

        opponent_type = "🤖 Робот" if not opponent_id else "👤 Реальный игрок"
        opponent_rank = get_rank_display(opponent_rating)

        # Информация о битве
        text = f"""
        <b>⚔️ АРЕНА</b>

        <b>📊 ТВОЙ РАНГ:</b> {rank_display}
        ⭐ {user.arena_rating} рейтинга
        [{progress_bar}] {int(progress)}%
        {needed} очков до повышения

        <b>👹 ПРОТИВНИК:</b> {opponent_type}
        {opponent_rank} ({opponent_rating}⭐)

        ⚡ <b>Нажми кнопку чтобы начать битву!</b>
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


@router.callback_query(F.data == "arena_top")
async def show_arena_top(callback: types.CallbackQuery):
    """Показать топ игроков арены"""
    try:
        async with AsyncSessionLocal() as session:
            # Получаем топ-10 игроков по рейтингу
            result = await session.execute(
                select(User)
                .where(User.arena_wins + User.arena_losses > 0)  # Игроки с боями
                .order_by(User.arena_rating.desc())
                .limit(10)
            )
            top_players = result.scalars().all()

            # Получаем карты в колодах топ-игроков для отображения
            text = "<b>🏆 ТОП-10 ИГРОКОВ АРЕНЫ</b>\n\n"

            from game.arena_ranks import get_rank_display

            for i, player in enumerate(top_players, 1):
                rank_display = get_rank_display(player.arena_rating)
                win_rate = (player.arena_wins / (player.arena_wins + player.arena_losses) * 100) if (player.arena_wins + player.arena_losses) > 0 else 0

                # Получаем информацию о колоде
                deck_info = ""
                if player.selected_deck:
                    deck_result = await session.execute(
                        select(Card.card_name, Card.rarity)
                        .join(UserCard, UserCard.card_id == Card.id)
                        .where(UserCard.id.in_(player.selected_deck[:5]))  # Топ-5 карты
                    )
                    top_cards = deck_result.all()
                    if top_cards:
                        deck_info = " | ".join([f"{name} [{rarity}]" for name, rarity in top_cards])

                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
                text += f"{medal} <b>{i}. {player.first_name}</b>\n"
                text += f"   {rank_display} | {player.arena_rating}⭐\n"
                text += f"   Побед: {player.arena_wins} | Винрейт: {win_rate:.1f}%\n"
                if deck_info:
                    text += f"   🃏 {deck_info}\n"
                text += "\n"

            # Добавляем информацию о пользователе
            user = await get_user_or_create(session, callback.from_user.id)

            # Находим место пользователя в топе
            user_position = 0
            if user.arena_wins + user.arena_losses > 0:
                user_pos_result = await session.execute(
                    select(func.count())
                    .select_from(User)
                    .where(
                        User.arena_rating > user.arena_rating,
                        User.arena_wins + User.arena_losses > 0
                    )
                )
                higher_count = user_pos_result.scalar()
                user_position = higher_count + 1

            rank_display = get_rank_display(user.arena_rating)
            win_rate = (user.arena_wins / (user.arena_wins + user.arena_losses) * 100) if (user.arena_wins + user.arena_losses) > 0 else 0

            text += f"<b>📊 ТВОЕ МЕСТО:</b> {user_position}\n"
            text += f"{rank_display} | {user.arena_rating}⭐\n"
            text += f"Побед: {user.arena_wins} | Винрейт: {win_rate:.1f}%\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚔️ НА АРЕНУ", callback_data="open_arena")],
                [InlineKeyboardButton(text="« Вернуться", callback_data="back_to_main")]
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка show_arena_top: {e}")
        await callback.answer("❌ Ошибка загрузки топа", show_alert=True)


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

        # Обрабатываем результат битвы
        if action == "battle_result":
            logger.info(f"🎯 Processing battle result: {result}")

            async with AsyncSessionLocal() as session:
                user = await get_user_or_create(session, message.from_user.id)

                # Начисляем награды
                if result == "win":
                    rating_change = rewards.get("rating", 20)
                    coins_reward = rewards.get("coins", 50)
                    dust_reward = rewards.get("dust", 50)

                    user.arena_wins += 1
                    user.arena_rating += rating_change
                    user.coins += coins_reward
                    user.dust += dust_reward

                elif result == "lose":
                    rating_change = rewards.get("rating", -15)
                    coins_reward = rewards.get("coins", 25)
                    dust_reward = rewards.get("dust", 25)

                    user.arena_losses += 1
                    user.arena_rating = max(0, user.arena_rating + rating_change)
                    user.coins += coins_reward
                    user.dust += dust_reward

                await session.commit()

                logger.info(f"✅ User updated: wins={user.arena_wins}, rating={user.arena_rating}")

                # Убираем клавиатуру арены
                from aiogram.types import ReplyKeyboardRemove

                await message.answer(
                    f"{'🎉' if result == 'win' else '😔'} <b>БИТВА ЗАВЕРШЕНА!</b>\n\n"
                    f"💰 Получено: +{coins_reward}💰 +{dust_reward}✨\n"
                    f"⭐ Рейтинг: {user.arena_rating}",
                    reply_markup=ReplyKeyboardRemove()
                )

                # Удаляем битву из Redis
                if battle_id:
                    await battle_storage.delete_battle(battle_id)

    except Exception as e:
        logger.exception(f"❌ Ошибка обработки WebApp данных: {e}")
        await message.answer(json.dumps({"type": "error", "message": str(e)}))
