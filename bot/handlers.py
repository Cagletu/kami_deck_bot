# bot/handlers.py
from aiogram import Router, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from database.base import AsyncSessionLocal
from database.models.user import User
import logging

from database.crud import (
    get_user_or_create,
    get_user_collection,
    get_collection_stats,
    open_pack,
    start_expedition,
    claim_expedition
)
from database.models.expedition import ExpeditionType, ExpeditionStatus
from bot.keyboards import (
    main_menu_keyboard,
    collection_menu_keyboard,
    rarity_keyboard,
    expedition_type_keyboard
)

router = Router()

logger = logging.getLogger(__name__)

# ===== START =====
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    user = await get_user_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    welcome_text = f"""
🎮 <b>Добро пожаловать в Kami Deck</b>, {message.from_user.first_name}!

<b>📊 Ваш профиль:</b>
👤 Уровень: <code>{user.level}</code>
💰 Монеты: <code>{user.coins}</code>
✨ Пыль: <code>{user.dust}</code>
🃏 Карточек: <code>{user.cards_opened or 0}</code>

<b>🏆 Статистика:</b>
⚔️ Рейтинг: <code>{user.arena_rating}</code>
📈 Побед/Поражений: <code>{user.arena_wins}/{user.arena_losses}</code>
🏕️ Слотов экспедиций: <code>{user.expeditions_slots}</code>

<b>🎯 Доступные команды:</b>
/profile - Ваш профиль
/collection - Коллекция карт
/open_pack - Открыть пачку (100 монет)
/expedition - Экспедиции
/daily - Ежедневная награда
/help - Помощь по игре
"""
    await message.answer(welcome_text, reply_markup=main_menu_keyboard())

# ===== PROFILE =====
@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user = await get_user_or_create(message.from_user.id)
    
    total_battles = user.arena_wins + user.arena_losses
    win_rate = (user.arena_wins / total_battles * 100) if total_battles > 0 else 0
    time_in_game = datetime.now() - user.created_at
    days = time_in_game.days
    hours = time_in_game.seconds // 3600
    
    stats = await get_collection_stats(user.id)
    
    profile_text = f"""
<b>📊 ПРОФИЛЬ ИГРОКА</b>

<b>👤 Основное:</b>
ID: <code>{user.id}</code>
Имя: {user.first_name}
Уровень: <code>{user.level}</code>

<b>💰 Ресурсы:</b>
Монеты: <code>{user.coins}</code>
Пыль: <code>{user.dust}</code>
Слотов экспедиций: <code>{user.expeditions_slots}</code>

<b>🃏 Коллекция:</b>
Всего карт: <code>{user.cards_opened or 0}</code>
SSS: {stats['SSS']} | ASS: {stats['ASS']} | S: {stats['S']}
A: {stats['A']} | B: {stats['B']} | C: {stats['C']}
D: {stats['D']} | E: {stats['E']}

<b>🏆 Статистика:</b>
Побед: <code>{user.arena_wins}</code>
Поражений: <code>{user.arena_losses}</code>
Винрейт: <code>{win_rate:.1f}%</code>
Рейтинг: <code>{user.arena_rating}</code>

<b>⏰ Время в игре:</b>
В игре: {days} дней, {hours} часов
"""
    await message.answer(profile_text)

# ===== COLLECTION =====
@router.message(Command("collection"))
async def cmd_collection(message: types.Message):
    user = await get_user_or_create(message.from_user.id)
    stats = await get_collection_stats(user.id)
    
    collection_text = f"""
<b>🃏 КОЛЛЕКЦИЯ КАРТ</b>

Всего карт: <code>{user.cards_opened or 0}</code>

<b>📊 По редкостям:</b>
🏆 SSS: <code>{stats['SSS']}</code> | ✨ ASS: <code>{stats['ASS']}</code> | ⭐ S: <code>{stats['S']}</code>
🔮 A: <code>{stats['A']}</code> | 💫 B: <code>{stats['B']}</code> | ⚡ C: <code>{stats['C']}</code>
🟢 D: <code>{stats['D']}</code> | ⚪ E: <code>{stats['E']}</code>

<b>🎯 Выберите способ просмотра:</b>
"""
    await message.answer(collection_text, reply_markup=collection_menu_keyboard())

@router.callback_query(lambda c: c.data == "collection_by_rarity")
async def collection_by_rarity(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "<b>Выберите редкость для просмотра:</b>",
        reply_markup=rarity_keyboard()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("rarity_"))
async def show_rarity_collection(callback: types.CallbackQuery):
    rarity = callback.data.replace("rarity_", "").upper()
    user = await get_user_or_create(callback.from_user.id)
    
    cards, total = await get_user_collection(
        user.id,
        rarity_filter=rarity,
        page_size=5
    )
    
    if not cards:
        await callback.message.edit_text(
            f"<b>У вас нет карт редкости {rarity}</b>\n\n"
            f"Откройте пачку чтобы получить новые карты: /open_pack",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="« Назад", callback_data="collection_by_rarity")]
            ])
        )
        await callback.answer()
        return
    
    text = f"<b>📊 Карты редкости {rarity}</b>\n\n"
    
    for i, (user_card, card) in enumerate(cards, 1):
        text += f"{i}. <b>{card.card_name}</b>\n"
        text += f"   ⚔️ Ур.{user_card.level} | 💪{user_card.current_power}\n"
        text += f"   🎬 {card.anime_name[:30]}...\n\n"
    
    text += f"<i>Показано {len(cards)} из {total} карт</i>"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="« Назад", callback_data="collection_by_rarity"),
            InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_collection")
        ]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# ===== OPEN PACK =====
@router.message(Command("open_pack"))
async def cmd_open_pack(message: types.Message):
    user = await get_user_or_create(message.from_user.id)
    
    if user.coins < 100:
        await message.answer(
            "❌ Недостаточно монет!\n"
            "💰 Получите ежедневную награду: /daily\n"
            "🏕️ Или отправьте персонажей в экспедицию: /expedition"
        )
        return
    
    try:
        cards, pack_open = await open_pack(user.id, "common")
        async with AsyncSessionLocal() as session:
            updated_user = await session.get(User, user.id)
            
        # Формируем сообщение
        text = f"""
<b>📦 ВЫ ОТКРЫЛИ ПАЧКУ КАРТ!</b>

💰 Потрачено: <code>100</code> монет
💰 Осталось: <code>{updated_user.coins}</code> монет

<b>🎉 Вы получили:</b>
"""
        
        for card in cards:
            emoji = {
                'E': '⚪', 'D': '🟢', 'C': '⚡',
                'B': '💫', 'A': '🔮', 'S': '⭐',
                'ASS': '✨', 'SSS': '🏆'
            }.get(card.rarity, '🃏')
            
            text += f"{emoji} <b>{card.card_name}</b> [{card.rarity}]\n"
        
        if pack_open.guaranteed_rarity:
            text += f"\n🎁 <b>ГАРАНТИЯ!</b> Вам выпала {pack_open.guaranteed_rarity} карта!"
        
        # Отправляем первую картинку
        await message.answer_photo(
            photo=cards[0].original_url,
            caption=text
        )
        
        # Отправляем остальные карты (опционально)
        if len(cards) > 1:
            media_group = []
            for card in cards[1:]:
                media_group.append(types.InputMediaPhoto(
                    media=card.original_url,
                    caption=f"{card.card_name} [{card.rarity}]"
                ))
            await message.answer_media_group(media_group)
            
    except ValueError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        logger.error(f"Ошибка открытия пачки: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

# ===== EXPEDITION =====
@router.message(Command("expedition"))
async def cmd_expedition(message: types.Message):
    user = await get_user_or_create(message.from_user.id)
    
    # TODO: Показать активные экспедиции
    text = f"""
<b>🏕️ ЭКСПЕДИЦИИ</b>

Слотов: <code>{user.expeditions_slots}</code>

Выберите длительность экспедиции:
• 🕐 30 мин - 6-9 монет, 1 пыль, 50% шанс E карты
• 🕑 2 часа - 24-36 монет, 4 пыли, 100% шанс D карты
• 🕕 6 часов - 72-108 монет, 12 пыли, 100% шанс C карты

💡 <b>Бонус:</b> +50% награды за карты из одного аниме!
"""
    await message.answer(text, reply_markup=expedition_type_keyboard())

# ===== DAILY =====
@router.message(Command("daily"))
async def cmd_daily(message: types.Message):
    user = await get_user_or_create(message.from_user.id)
    
    # Проверяем не получал ли сегодня
    if user.last_daily_tasks and user.last_daily_tasks.date() == datetime.now().date():
        await message.answer(
            "❌ Вы уже получили ежедневную награду сегодня!\n"
            "Заходите завтра в 00:00 по МСК"
        )
        return
    
    reward_coins = 100
    reward_dust = 10
    
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        db_user.coins += reward_coins
        db_user.dust += reward_dust
        db_user.last_daily_tasks = datetime.now()
        await session.commit()
    
    text = f"""
<b>🎁 ЕЖЕДНЕВНАЯ НАГРАДА</b>

💰 Получено: <code>{reward_coins}</code> монет
✨ Получено: <code>{reward_dust}</code> пыли

💰 Теперь у вас: <code>{user.coins + reward_coins}</code> монет
✨ Пыли: <code>{user.dust + reward_dust}</code>

<b>📅 Заходите завтра снова!</b>
"""
    await message.answer(text)

# ===== HELP =====
@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = """
<b>❓ ПОМОЩЬ ПО ANIME CARDS GAME</b>

<b>📋 Основные команды:</b>
/start - Начало игры
/profile - Подробная статистика
/collection - Коллекция карт
/open_pack - Открыть пачку (100 монет)
/expedition - Экспедиции
/daily - Ежедневная награда
/help - Эта справка

<b>🎮 ИГРОВЫЕ МЕХАНИКИ:</b>

🏕️ <b>Экспедиции</b>
• Отправляйте карты в поход
• Чем дольше - тем больше награда
• Бонус за карты из одного аниме

📦 <b>Пачки карт</b>
• 5 карт в пачке
• Pity-система: A каждые 10 пачек, S каждые 30
• Чем выше редкость - тем сильнее карта

⭐ <b>Улучшение карт</b>
• Распыляйте дубли на пыль
• Улучшайте любимые карты
• Максимальный уровень: 100

⚔️ <b>Арена (скоро)</b>
• Сражайтесь с другими игроками
• Победа повышает рейтинг
• Даже проигрыш дает награду

🔄 <b>Обмен (скоро)</b>
• Меняйтесь картами с друзьями
• Только S и выше
• Уровень сбрасывается

<b>💰 Валюта:</b>
• 🟡 Монеты - за экспедиции и дейлики
• 💎 Пыль - за распыление дублей

<b>🆘 Поддержка:</b>
@Cagletu
"""
    await message.answer(help_text)

# ===== CALLBACK BACK BUTTONS =====
@router.callback_query(lambda c: c.data == "back_to_collection")
async def back_to_collection(callback: types.CallbackQuery):
    await cmd_collection(callback.message)
    await callback.answer()


