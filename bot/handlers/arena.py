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
            .where(
                and_(
                    UserCard.user_id == user_id,
                    UserCard.is_in_deck == True
                )
            )
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
                func.coalesce(func.json_array_length(User.selected_deck), 0) >= 5
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
        result = await session.execute(
            select(Card)
            .order_by(func.random())
            .limit(5)
        )
        cards = result.scalars().all()

        test_deck = []
        for i, card in enumerate(cards):
            level = random.randint(5, 20)

            # Рассчитываем характеристики на основе уровня
            power = int(card.base_power * (1 + (level - 1) * 0.06))  # +6% за уровень
            health = int(card.base_health * (1 + (level - 1) * 0.04))  # +4% за уровень
            attack = int(card.base_attack * (1 + (level - 1) * 0.07))  # +7% за уровень
            defense = int(card.base_defense * (1 + (level - 1) * 0.04))  # +4% за уровень

            # Добавляем бонус редкости
            rarity_mult = {
                'E': 1.0, 'D': 1.1, 'C': 1.2, 'B': 1.3,
                'A': 1.45, 'S': 1.65, 'ASS': 1.8, 'SSS': 2.0
            }.get(card.rarity, 1.0)

            power = int(power * rarity_mult)
            health = int(health * rarity_mult)
            attack = int(attack * rarity_mult)
            defense = int(defense * rarity_mult)

            test_deck.append((
                type('UserCard', (), {
                    'id': -i-1,
                    'user_id': -1,
                    'card_id': card.id,
                    'level': level,
                    'current_power': power,
                    'current_health': health,
                    'current_attack': attack,
                    'current_defense': defense,
                    'is_in_deck': True
                }),
                card
            ))

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
            position=i
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
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🃏 К коллекции", callback_data="collection_by_rarity")]
                ])
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
            "created_at": datetime.now().isoformat()
        }

        logger.info(f"Saving battle {battle_id} to Redis: {len(battle_data['player_cards'])} player cards, {len(battle_data['enemy_cards'])} enemy cards")
        await battle_storage.save_battle(battle_id, battle_data)

        # Создаем клавиатуру с WebApp
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⚔️ НАЧАТЬ БИТВУ",
                web_app=WebAppInfo(url=f"{WEBAPP_URL}?battle_id={battle_id}")
            )],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
        ])

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
        data = json.loads(message.web_app_data.data)
        action = data.get('action')
        battle_id = data.get('battle_id')
        logger.info(f"WebApp data received: action={action}, battle_id={battle_id}")

        # ===== ОБРАБОТКА РЕЗУЛЬТАТА БИТВЫ =====
        if action == 'battle_result':
            result = data.get('result')
            rewards = data.get('rewards', {})

            # ВАЖНО: если rewards пустые, используем стандартные
            if not rewards:
                rewards = {
                    'win': {'coins': 50, 'dust': 50, 'rating': 20},
                    'lose': {'coins': 25, 'dust': 25, 'rating': -15}
                }.get(result, {})

            logger.info(f"Battle result: {result}, rewards: {rewards}")

            async with AsyncSessionLocal() as session:
                user = await get_user_or_create(session, message.from_user.id)

                # Сохраняем старые значения для отчета
                old_stats = {
                    'wins': user.arena_wins,
                    'losses': user.arena_losses,
                    'rating': user.arena_rating,
                    'coins': user.coins,
                    'dust': user.dust
                }

                # Начисляем награды
                if result == 'win':
                    user.arena_wins += 1
                    user.arena_rating += rewards.get('rating', 20)
                    user.coins += rewards.get('coins', 50)
                    user.dust += rewards.get('dust', 50)
                elif result == 'lose':
                    user.arena_losses += 1
                    rating_change = rewards.get('rating', -15)
                    user.arena_rating = max(0, user.arena_rating + rating_change)
                    user.coins += rewards.get('coins', 25)
                    user.dust += rewards.get('dust', 25)

                # Сохраняем битву в БД
                battle_data = await battle_storage.get_battle(battle_id) if battle_id else None
                if battle_data:
                    db_battle = DBArenaBattle(
                        attacker_id=user.id,
                        defender_id=battle_data.get("opponent_id") or -1,
                        attacker_deck=[c.get("user_card_id") for c in battle_data.get("player_cards", []) if c.get("user_card_id", 0) > 0],
                        defender_deck=[c.get("user_card_id") for c in battle_data.get("enemy_cards", []) if c.get("user_card_id", 0) > 0],
                        rounds=battle_data.get("turn", 0),
                        winner_id=user.id if result == 'win' else None,
                        result="attacker_win" if result == 'win' else "defender_win",
                        attacker_rating_change=rewards.get('rating', 20) if result == 'win' else rating_change,
                        attacker_reward_coins=rewards.get('coins', 50) if result == 'win' else rewards.get('coins', 25),
                        attacker_reward_dust=rewards.get('dust', 50) if result == 'win' else rewards.get('dust', 25),
                        ended_at=datetime.now()
                    )
                    session.add(db_battle)

                await session.commit()
                await session.refresh(user)

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

            return

        # ===== ОСТАЛЬНАЯ ОБРАБОТКА =====
        if action == 'close_arena':
            logger.info(f"User {message.from_user.id} closed arena")
            return

        if not battle_id:
            return

        # Получаем состояние боя из Redis
        battle_data = await battle_storage.get_battle(battle_id)
        if not battle_data:
            await message.answer(json.dumps({
                "type": "error",
                "message": "Битва не найдена или истекло время"
            }))
            return

        if action == 'next_turn':
            async with AsyncSessionLocal() as session:
                user = await get_user_or_create(session, message.from_user.id)
                
            # Восстанавливаем карты из сохраненных данных
            user_cards = []
            for user_card_id, card_id in battle_data["user_deck"]:
                    result = await session.execute(
                        select(UserCard, Card)
                        .join(Card, UserCard.card_id == Card.id)
                        .where(UserCard.id == user_card_id)
                    )
                    data = result.first()
                    if data:
                        user_cards.append(data)

            opponent_cards = []
            for user_card_id, card_id in battle_data["opponent_deck"]:
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(UserCard, Card)
                        .join(Card, UserCard.card_id == Card.id)
                        .where(UserCard.id == user_card_id)
                    )
                    data = result.first()
                    if data:
                        opponent_cards.append(data)

            if not opponent_cards:
                opponent_cards, _ = await generate_test_deck()

            # Создаем бой с текущим состоянием
            user_battle_cards = prepare_battle_cards(user_cards, is_user=True)
            opponent_battle_cards = prepare_battle_cards(opponent_cards, is_user=False)

            battle = ArenaBattle(user_battle_cards, opponent_battle_cards)

            # Выполняем один ход
            actions = battle.next_turn()

            # Проверяем окончание боя
            if battle.winner:
                async with AsyncSessionLocal() as session:
                    user = await get_user_or_create(session, message.from_user.id)

                    # Сохраняем в БД
                    db_battle = DBArenaBattle(
                        attacker_id=user.id,
                        defender_id=battle_data.get("opponent_id") or -1,
                        attacker_deck=[uc.id for uc, _ in user_cards],
                        defender_deck=[uc.id for uc, _ in opponent_cards] if battle_data.get("opponent_id") else [],
                        rounds=battle.turn,
                        attacker_damage=sum(a.damage for a in battle.actions if a.attacker_id > 0),
                        defender_damage=sum(a.damage for a in battle.actions if a.attacker_id < 0),
                        attacker_rating_before=user.arena_rating,
                        defender_rating_before=1000,
                        ended_at=datetime.now()
                    )

                    if battle.winner == 'user':
                        db_battle.winner_id = user.id
                        db_battle.result = "attacker_win"
                        db_battle.attacker_rating_change = 20
                        db_battle.attacker_reward_coins = 50
                        db_battle.attacker_reward_dust = 50

                        user.arena_wins += 1
                        user.arena_rating += 20
                        user.coins += 150
                        user.dust += 25
                    else:
                        db_battle.result = "defender_win"
                        db_battle.attacker_rating_change = -15
                        db_battle.attacker_reward_coins = 25
                        db_battle.attacker_reward_dust = 25

                        user.arena_losses += 1
                        user.arena_rating = max(0, user.arena_rating - 5)
                        user.coins += 50
                        user.dust += 10

                    session.add(db_battle)
                    await session.commit()

                # Удаляем из Redis
                await battle_storage.delete_battle(battle_id)

            # Обновляем состояние в Redis
            battle_data["state"] = battle.get_battle_state()
            await battle_storage.save_battle(battle_id, battle_data)

            # Отправляем обновление
            await message.answer(json.dumps({
                "type": "battle_update",
                "state": battle.get_battle_state(),
                "actions": [
                    {
                        "attacker_id": a.attacker_id,
                        "attacker_name": a.attacker_name,
                        "defender_id": a.defender_id,
                        "defender_name": a.defender_name,
                        "damage": a.damage,
                        "is_critical": a.is_critical,
                        "is_dodged": a.is_dodged
                    }
                    for a in actions
                ]
            }))

    except Exception as e:
        logger.exception(f"Ошибка обработки WebApp данных: {e}")
        await message.answer(json.dumps({
            "type": "error",
            "message": str(e)
        }))
                             