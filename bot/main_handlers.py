# bot/handlers.py
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import datetime
from database.base import AsyncSessionLocal
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
import logging

from database.models.user import User
from database.models.user_card import UserCard
from database.models.card import Card
from database.crud_cards import get_user_card_detail, toggle_favorite, toggle_in_deck, upgrade_user_card
from game.upgrade_calculator import get_upgrade_cost
from game.duplicate_system import check_for_duplicate, process_duplicate
from sqlalchemy import func, and_

from sqlalchemy import select
from aiogram.types import WebAppInfo

from database.crud import (
    get_user_or_create,
    get_collection_stats,
    open_pack,
    get_user_cards_paginated,
    get_user_collection,
)
from bot.keyboards import (
    main_menu_keyboard,
    collection_menu_keyboard,
    rarity_keyboard,
    collection_keyboard,
    card_detail_keyboard,
)

# URL для WebApp (ваш Railway домен)
WEBAPP_URL = "https://kamideckbot-production.up.railway.app/arena.html"

router = Router()
logger = logging.getLogger(__name__)

# 1. Команды (message handlers)


# ===== START =====
@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(
                session,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name)

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

    except Exception as e:
        logger.exception(f"Ошибка в хендлере cmd_start: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


# ===== PROFILE =====
@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, message.from_user.id)

        total_battles = user.arena_wins + user.arena_losses
        win_rate = (user.arena_wins / total_battles *
                    100) if total_battles > 0 else 0
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
🏆 SSS: {stats.get('SSS', 0)} | ✨ ASS: {stats.get('ASS', 0)} | ⭐ S: {stats.get('S', 0)}
🔮 A: {stats.get('A', 0)} | 💫 B: {stats.get('B', 0)} | ⚡ C: {stats.get('C', 0)}
🟢 D: {stats.get('D', 0)} | ⚪ E: {stats.get('E', 0)}

<b>🏆 Статистика:</b>
Побед: <code>{user.arena_wins}</code>
Поражений: <code>{user.arena_losses}</code>
Винрейт: <code>{win_rate:.1f}%</code>
Рейтинг: <code>{user.arena_rating}</code>

<b>⏰ Время в игре:</b>
В игре: {days} дней, {hours} часов
"""
        await message.answer(profile_text)

    except Exception as e:
        logger.exception(f"Ошибка в хендлере cmd_profile: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


# ===== COLLECTION =====
@router.message(Command("collection"))
async def cmd_collection(message: types.Message):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, message.from_user.id)

        stats = await get_collection_stats(user.id)

        collection_text = f"""
<b>🃏 КОЛЛЕКЦИЯ КАРТ</b>

Всего карт: <code>{user.cards_opened or 0}</code>

<b>📊 По редкостям:</b>
🏆 SSS: <code>{stats.get('SSS', 0)}</code> | ✨ ASS: <code>{stats.get('ASS', 0)}</code> | ⭐ S: <code>{stats.get('S', 0)}</code>
🔮 A: <code>{stats.get('A', 0)}</code> | 💫 B: <code>{stats.get('B', 0)}</code> | ⚡ C: <code>{stats.get('C', 0)}</code>
🟢 D: <code>{stats.get('D', 0)}</code> | ⚪ E: <code>{stats.get('E', 0)}</code>

<b>🎯 Выберите способ просмотра:</b>
"""
        await message.answer(collection_text,
                             reply_markup=collection_menu_keyboard())

    except Exception as e:
        logger.exception(f"Ошибка в хендлере cmd_collection: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


# ===== OPEN PACK =====


@router.message(Command("open_pack"))
async def cmd_open_pack(message: types.Message):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(
                session,
                message.from_user.id,
                message.from_user.username,
                message.from_user.first_name,
                message.from_user.last_name
            )

            if user.coins < 100:
                await message.answer(
                    "❌ Недостаточно монет!\n"
                    "💰 Получите ежедневную награду: /daily\n"
                    "🏕️ Или отправьте персонажей в экспедицию: /expedition"
                )
                return

            cards, pack_open, new_card_ids = await open_pack(user.id, "common", session)

            # Проверяем каждую карту на дубликат
            new_cards = []
            duplicates = []
            total_dust = 0

            for i, card in enumerate(cards):
                # Проверяем, есть ли уже такая карта у пользователя
                check = await check_for_duplicate(session, user.id, card.id)

                if check["is_duplicate"]:
                    # Это дубликат - начисляем пыль
                    await process_duplicate(session, user.id, card.id, check["dust_earned"])
                    duplicates.append({
                        "card": card,
                        "dust": check["dust_earned"]
                    })
                    total_dust += check["dust_earned"]
                else:
                    # Это новая карта - добавляем в коллекцию
                    user_card = UserCard(
                        user_id=user.id,
                        card_id=card.id,
                        level=1,
                        current_power=card.base_power,
                        current_health=card.base_health,
                        current_attack=card.base_attack,
                        current_defense=card.base_defense,
                        source="pack"
                    )
                    session.add(user_card)
                    new_cards.append(card)

            # Обновляем счетчик карт пользователя
            user.cards_opened = (user.cards_opened or 0) + len(new_cards)

            await session.commit()
            await session.refresh(user)

        # Формируем сообщение
        text = f"<b>📦 ВЫ ОТКРЫЛИ ПАЧКУ КАРТ!</b>\n\n💰 Потрачено: <code>100</code> монет\n💰 Осталось: <code>{user.coins}</code> монет\n\n"

        if duplicates:
            text += "\n<b>🔄 ДУБЛИКАТЫ ПРЕВРАЩЕНЫ В ПЫЛЬ:</b>\n"
            for dup in duplicates:
                emoji = {'E':'⚪','D':'🟢','C':'⚡','B':'💫','A':'🔮','S':'⭐','ASS':'✨','SSS':'🏆'}.get(dup['card'].rarity,'🃏')
                text += f"{emoji} {dup['card'].card_name} [{dup['card'].rarity}] → +{dup['dust']}✨\n"
            text += f"\n<b>✨ Всего получено пыли:</b> {total_dust}✨\n"

        if new_cards:
            text += "\n<b>🎉 НОВЫЕ КАРТЫ В КОЛЛЕКЦИИ:</b>\n"
            for card in new_cards:
                emoji = {'E':'⚪','D':'🟢','C':'⚡','B':'💫','A':'🔮','S':'⭐','ASS':'✨','SSS':'🏆'}.get(card.rarity,'🃏')
                text += f"{emoji} <b>{card.card_name}</b> [{card.rarity}]\n"

        if pack_open.guaranteed_rarity:
            text += f"\n🎁 <b>ГАРАНТИЯ!</b> Вам выпала {pack_open.guaranteed_rarity} карта!"

        # Отправляем первую карту (если есть новые) или первую из дубликатов
        first_card = new_cards[0] if new_cards else (duplicates[0]["card"] if duplicates else None)
        if first_card:
            await message.answer_photo(photo=first_card.original_url, caption=text)

        # Отправляем остальные карты
        all_cards = new_cards + [d["card"] for d in duplicates]
        if len(all_cards) > 1:
            media_group = []
            for card in all_cards[1:]:
                is_new = card in new_cards
                caption = f"{'✨ НОВАЯ' if is_new else '🔄 ДУБЛИКАТ'} {card.card_name} [{card.rarity}]"
                media_group.append(types.InputMediaPhoto(media=card.original_url, caption=caption))

            if media_group:
                await message.answer_media_group(media_group)

    except ValueError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        logger.exception(f"Ошибка открытия пачки: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

# ===== DAILY =====
@router.message(Command("daily"))
async def cmd_daily(message: types.Message):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, message.from_user.id)

            if user.last_daily_tasks and user.last_daily_tasks.date(
            ) == datetime.now().date():
                await message.answer(
                    "❌ Вы уже получили ежедневную награду сегодня!\nЗаходите завтра в 00:00 по МСК"
                )
                return

            reward_coins = 100
            reward_dust = 10

            db_user = await session.get(User, user.id)
            db_user.coins += reward_coins
            db_user.dust += reward_dust
            db_user.last_daily_tasks = datetime.now()
            await session.commit()

            # Обновляем данные пользователя
            user.coins = db_user.coins
            user.dust = db_user.dust

        text = f"""
<b>🎁 ЕЖЕДНЕВНАЯ НАГРАДА</b>

💰 Получено: <code>{reward_coins}</code> монет
✨ Получено: <code>{reward_dust}</code> пыли

💰 Теперь у вас: <code>{user.coins}</code> монет
✨ Пыли: <code>{user.dust}</code>

<b>📅 Заходите завтра снова!</b>
"""
        await message.answer(text)

    except Exception as e:
        logger.exception(f"Ошибка cmd_daily: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


# ===== HELP =====
@router.message(Command("help"))
async def cmd_help(message: types.Message):
    try:
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

    except Exception as e:
        logger.exception(f"Ошибка cmd_help: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.message(Command("cancel"), StateFilter("*"))
async def cancel_any(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено")


# ===== CALLBACKS =====
# 2. Специфичные callback-хендлеры


# Callback для редкости и возврата
@router.callback_query(F.data == "collection_by_rarity")
async def collection_by_rarity(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            "<b>Выберите редкость для просмотра:</b>",
            reply_markup=rarity_keyboard())
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка collection_by_rarity: {e}")
        await callback.answer("❌ Произошла ошибка.")


@router.callback_query(F.data.startswith("rarity_"))
async def show_rarity_collection(callback: types.CallbackQuery):
    """Показать коллекцию карт по редкости"""
    try:
        # Парсим callback_data: rarity_SSS_1 или rarity_SSS
        parts = callback.data.split("_")
        rarity = parts[1].upper()
        page = int(parts[2]) if len(parts) > 2 else 1

        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)
            cards, total, total_pages = await get_user_collection(
                user.id,
                page=page,
                page_size=5,  # Показываем по 5 карт на странице
                rarity_filter=rarity)

        if not cards:
            await callback.message.edit_text(
                f"<b>У вас нет карт редкости {rarity}</b>\n\n"
                f"Откройте пачку чтобы получить новые карты: /open_pack",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="« Назад",
                                         callback_data="collection_by_rarity")
                ]]))
            await callback.answer()
            return

        # Формируем текст
        text = f"<b>📊 Карты редкости {rarity}</b>\n\n"

        # Сохраняем ID карт для кнопок просмотра
        card_ids = []

        for i, (user_card, card) in enumerate(cards, 1):
            # Статус карты
            status = ""
            if user_card.is_favorite:
                status = "⭐ "
            elif user_card.is_in_deck:
                status = "⚔️ "
            elif user_card.is_in_expedition:
                status = "🏕️ "

            # Обрезаем длинные названия аниме
            anime_name = card.anime_name
            if anime_name and len(anime_name) > 25:
                anime_name = anime_name[:22] + "..."

            # Добавляем информацию о карте
            text += f"{i}. {status}<b>{card.card_name}</b>\n"
            text += f"   📈 Ур.{user_card.level} | 💪 {user_card.current_power}\n"
            text += f"   🎬 {anime_name or 'Неизвестно'}\n\n"

            # Сохраняем ID для кнопки
            card_ids.append(user_card.id)

        text += f"<i>Страница {page} из {total_pages} • Всего {total} карт</i>"

        # Строим клавиатуру
        keyboard = []

        # Кнопки навигации по страницам
        nav_buttons = []
        if page > 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="◀️", callback_data=f"rarity_{rarity}_{page-1}"))

        nav_buttons.append(
            InlineKeyboardButton(text=f"{page}/{total_pages}",
                                 callback_data="noop"))

        if page < total_pages:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="▶️", callback_data=f"rarity_{rarity}_{page+1}"))

        keyboard.append(nav_buttons)

        # Кнопки просмотра карт (максимум 5)
        view_row = []
        for idx, card_id in enumerate(card_ids[:5], 1):
            view_row.append(
                InlineKeyboardButton(text=f"🔍 {idx}",
                                     callback_data=f"view_card_{card_id}"))
        if view_row:
            keyboard.append(view_row)

        # Кнопки навигации по меню
        keyboard.append([
            InlineKeyboardButton(text="« К редкостям",
                                 callback_data="collection_by_rarity"),
            InlineKeyboardButton(text="🏠 В меню",
                                 callback_data="back_to_collection")
        ])

        await callback.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка show_rarity_collection: {e}")
        await callback.answer("❌ Произошла ошибка.")


@router.callback_query(F.data == "back_to_collection")
async def back_to_collection(callback: types.CallbackQuery):
    try:
        await cmd_collection(callback.message)
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка back_to_collection: {e}")
        await callback.answer("❌ Произошла ошибка.")


@router.callback_query(F.data == "open_pack")
async def cb_open_pack(callback: types.CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(
                session,
                callback.from_user.id,
                callback.from_user.username,
                callback.from_user.first_name,
                callback.from_user.last_name
            )

            if user.coins < 100:
                await callback.answer("Недостаточно монет!", show_alert=True)
                return

            # Открываем пачку
            cards, pack_open, new_card_ids = await open_pack(user.id, "common", session)

            # Проверяем дубликаты
            new_cards = []
            duplicates = []
            total_dust = 0

            for card in cards:
                check = await check_for_duplicate(session, user.id, card.id)

                if check["is_duplicate"]:
                    await process_duplicate(session, user.id, card.id, check["dust_earned"])
                    duplicates.append({
                        "card": card,
                        "dust": check["dust_earned"]
                    })
                    total_dust += check["dust_earned"]
                else:
                    user_card = UserCard(
                        user_id=user.id,
                        card_id=card.id,
                        level=1,
                        current_power=card.base_power,
                        current_health=card.base_health,
                        current_attack=card.base_attack,
                        current_defense=card.base_defense,
                        source="pack"
                    )
                    session.add(user_card)
                    new_cards.append(card)

            user.cards_opened = (user.cards_opened or 0) + len(new_cards)

            await session.commit()
            await session.refresh(user)

        # Формируем текст
        text = (
            f"<b>📦 ВЫ ОТКРЫЛИ ПАЧКУ КАРТ!</b>\n\n"
            f"💰 Потрачено: <code>100</code> монет\n"
            f"💰 Осталось: <code>{user.coins}</code> монет\n"
        )

        if duplicates:
            text += "\n<b>🔄 ДУБЛИКАТЫ ПРЕВРАЩЕНЫ В ПЫЛЬ:</b>\n"
            for dup in duplicates:
                emoji = {'E':'⚪','D':'🟢','C':'⚡','B':'💫','A':'🔮','S':'⭐','ASS':'✨','SSS':'🏆'}.get(dup['card'].rarity,'🃏')
                text += f"{emoji} {dup['card'].card_name} [{dup['card'].rarity}] → +{dup['dust']}✨\n"
            text += f"\n<b>✨ Всего получено пыли:</b> {total_dust}✨\n"

        if new_cards:
            text += "\n<b>🎉 НОВЫЕ КАРТЫ В КОЛЛЕКЦИИ:</b>\n"
            for card in new_cards:
                emoji = {'E':'⚪','D':'🟢','C':'⚡','B':'💫','A':'🔮','S':'⭐','ASS':'✨','SSS':'🏆'}.get(card.rarity,'🃏')
                text += f"{emoji} <b>{card.card_name}</b> [{card.rarity}]\n"

        if pack_open.guaranteed_rarity:
            text += f"\n🎁 <b>ГАРАНТИЯ!</b> Вам выпала {pack_open.guaranteed_rarity} карта!"

        # Первая карта
        first_card = new_cards[0] if new_cards else (duplicates[0]["card"] if duplicates else None)
        if first_card:
            await callback.message.answer_photo(photo=first_card.original_url, caption=text)

        # Остальные карты
        all_cards = new_cards + [d["card"] for d in duplicates]
        if len(all_cards) > 1:
            media_group = []
            for card in all_cards[1:]:
                is_new = card in new_cards
                caption = f"{'✨ НОВАЯ' if is_new else '🔄 ДУБЛИКАТ'} {card.card_name} [{card.rarity}]"
                media_group.append(types.InputMediaPhoto(media=card.original_url, caption=caption))

            if media_group:
                await callback.message.answer_media_group(media_group)

        await callback.answer()

    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
    except Exception as e:
        logger.exception(f"Ошибка открытия пачки: {e}")
        await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)




@router.callback_query(F.data.startswith("col_page:"))
async def cb_collection_page(callback: CallbackQuery):
    try:
        data_parts = callback.data.split(":")
        page = int(data_parts[1])
        rarity = data_parts[2] if len(data_parts) > 2 else None

        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)
            cards, has_next = await get_user_cards_paginated(session=session,
                                                             user_id=user.id,
                                                             page=page,
                                                             rarity=rarity)

        if not cards:
            await callback.answer("Больше карт нет")
            return

        card = cards[0]

        caption = (f"🃏 <b>{card.card.card_name}</b>\n"
                   f"⭐ {card.card.rarity}\n"
                   f"⚔️ {card.current_power}")

        await callback.message.edit_media(
            media=types.InputMediaPhoto(media=card.card.original_url,
                                        caption=caption),
            reply_markup=collection_keyboard(page, has_next, rarity))

        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка cb_collection_page: {e}")
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


# 3. Хендлеры действий с картами


@router.callback_query(F.data.startswith("favorite_"))
async def toggle_favorite_handler(callback: types.CallbackQuery):
    """Добавить/убрать из избранного"""
    try:
        card_id = int(callback.data.replace("favorite_", ""))
        logger.info(f"Избранное: карта {card_id}")

        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            result = await session.execute(
                select(UserCard).where(
                    and_(UserCard.id == card_id, UserCard.user_id == user.id)))
            user_card = result.scalar_one_or_none()

            if not user_card:
                await callback.answer("❌ Карта не найдена", show_alert=True)
                return

            user_card.is_favorite = not user_card.is_favorite
            await session.commit()

            status = "⭐ добавлена в избранное" if user_card.is_favorite else "☆ убрана из избранного"
            await callback.answer(status, show_alert=False)

            # Обновляем просмотр карты
            await view_card_detail(callback)

    except Exception as e:
        logger.exception(f"Ошибка favorite: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("deck_"))
async def toggle_deck_handler(callback: types.CallbackQuery):
    """Добавить/убрать из колоды"""
    try:
        card_id = int(callback.data.replace("deck_", ""))
        logger.info(f"Колода: карта {card_id}")

        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            # Проверяем количество карт в колоде
            deck_count = await session.execute(
                select(func.count()).select_from(UserCard).where(
                    and_(UserCard.user_id == user.id,
                         UserCard.is_in_deck == True)))
            deck_count = deck_count.scalar()

            result = await session.execute(
                select(UserCard).where(
                    and_(UserCard.id == card_id, UserCard.user_id == user.id)))
            user_card = result.scalar_one_or_none()

            if not user_card:
                await callback.answer("❌ Карта не найдена", show_alert=True)
                return

            # Если добавляем в колоду, проверяем лимит
            if not user_card.is_in_deck and deck_count >= 5:
                await callback.answer("❌ В колоде может быть только 5 карт!",
                                      show_alert=True)
                return

            user_card.is_in_deck = not user_card.is_in_deck
            await session.commit()

            status = "⚔️ карта добавлена в колоду" if user_card.is_in_deck else "📦 карта убрана из колоды"
            await callback.answer(status, show_alert=False)

            # Обновляем просмотр карты
            await view_card_detail(callback)

    except Exception as e:
        logger.exception(f"Ошибка deck: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("upgrade_"))
async def upgrade_card(callback: types.CallbackQuery):
    """Улучшить карту"""
    try:
        card_id = int(callback.data.replace("upgrade_", ""))
        logger.info(f"Улучшение карты ID: {card_id}")

        async with AsyncSessionLocal() as session:
            # Получаем пользователя
            user = await get_user_or_create(session, callback.from_user.id)
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return

            # Получаем карту
            result = await session.execute(
                select(UserCard, Card)
                .join(Card, UserCard.card_id == Card.id)
                .where(UserCard.id == card_id)
            )
            data = result.first()
            if not data:
                await callback.answer("Карта не найдена", show_alert=True)
                return

            user_card, card = data
            if user_card.user_id != user.id:
                await callback.answer("❌ Карта не принадлежит вам", show_alert=True)
                return

            if user_card.level >= 100:
                await callback.answer("Карта уже максимального уровня!", show_alert=True)
                return

            # Сохраняем старые статы
            old_stats = {
                'power': user_card.current_power,
                'health': user_card.current_health,
                'attack': user_card.current_attack,
                'defense': user_card.current_defense,
                'level': user_card.level
            }

            # Стоимость
            from game.upgrade_calculator import get_upgrade_cost, calculate_stats_for_level
            upgrade_cost = get_upgrade_cost(card, user_card.level)
            if user.dust < upgrade_cost:
                await callback.answer(f"❌ Не хватает пыли! Нужно: {upgrade_cost}", show_alert=True)
                return

            # Улучшаем
            user.dust -= upgrade_cost
            user_card.level += 1
            user_card.times_upgraded += 1
            user.total_cards_upgraded += 1

            new_stats = calculate_stats_for_level(card, user_card.level)
            user_card.current_power = new_stats['power']
            user_card.current_health = new_stats['health']
            user_card.current_attack = new_stats['attack']
            user_card.current_defense = new_stats['defense']

            await session.commit()

            # Разница
            diff_power = user_card.current_power - old_stats['power']
            diff_health = user_card.current_health - old_stats['health']
            diff_attack = user_card.current_attack - old_stats['attack']
            diff_defense = user_card.current_defense - old_stats['defense']

            # Прогресс до бонуса
            next_ten_bonus = ((user_card.level // 10) + 1) * 10
            levels_to_bonus = next_ten_bonus - user_card.level
            ten_level_progress = user_card.level % 10 or 10
            progress_bar = "█" * ten_level_progress + "░" * (10 - ten_level_progress)

            text = f"""
<b>✨ УЛУЧШЕНИЕ КАРТЫ</b>

<b>{card.card_name}</b> [{card.rarity}]
📈 <b>Уровень:</b> {old_stats['level']} → {user_card.level} (+1)

<b>⚔️ ИЗМЕНЕНИЕ ХАРАКТЕРИСТИК:</b>
💪 Сила:     {old_stats['power']} → {user_card.current_power} (+{diff_power})
❤️ Здоровье: {old_stats['health']} → {user_card.current_health} (+{diff_health})
⚔️ Атака:    {old_stats['attack']} → {user_card.current_attack} (+{diff_attack})
🛡️ Защита:   {old_stats['defense']} → {user_card.current_defense} (+{diff_defense})

<b>📊 ПРОГРЕСС:</b>
Бонус за 10 уровней: +5% ко всем статам
[{progress_bar}] {ten_level_progress}/10
{levels_to_bonus} ур. до следующего бонуса

💰 Потрачено пыли: {upgrade_cost}✨
📦 Осталось пыли: {user.dust}✨
"""

            # Кнопки вынесены в keyboards.py
            from bot.keyboards import upgrade_card_keyboard
            keyboard = upgrade_card_keyboard(card_id)

            await callback.message.edit_caption(caption=text, reply_markup=keyboard)
            await callback.answer(f"✨ Уровень повышен! (+{diff_power} силы)", show_alert=False)

    except Exception as e:
        logger.exception(f"Ошибка upgrade_card: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)



@router.callback_query(F.data == "profile")
async def callback_profile(callback: types.CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

        total_battles = user.arena_wins + user.arena_losses
        win_rate = (user.arena_wins / total_battles *
                    100) if total_battles > 0 else 0
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
🏆 SSS: {stats.get('SSS', 0)} | ✨ ASS: {stats.get('ASS', 0)} | ⭐ S: {stats.get('S', 0)}
🔮 A: {stats.get('A', 0)} | 💫 B: {stats.get('B', 0)} | ⚡ C: {stats.get('C', 0)}
🟢 D: {stats.get('D', 0)} | ⚪ E: {stats.get('E', 0)}

<b>🏆 Статистика:</b>
Побед: <code>{user.arena_wins}</code>
Поражений: <code>{user.arena_losses}</code>
Винрейт: <code>{win_rate:.1f}%</code>
Рейтинг: <code>{user.arena_rating}</code>

<b>⏰ Время в игре:</b>
В игре: {days} дней, {hours} часов
"""
        await callback.message.edit_text(profile_text)
        await callback.answer()  # Убирает "часики" загрузки

    except Exception as e:
        logger.exception(f"Ошибка в хендлере callback_profile: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка. Попробуйте позже.")
        await callback.answer()


@router.callback_query(F.data.startswith("5x_upgrade_"))
async def upgrade_card_5x(callback: types.CallbackQuery):
    """Улучшить карту 5 раз"""
    try:
        card_id = int(callback.data.replace("5x_upgrade_", ""))

        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            result = await session.execute(
                select(UserCard, Card)
                .join(Card, UserCard.card_id == Card.id)
                .where(UserCard.id == card_id)
            )
            data = result.first()
            if not data:
                await callback.answer("❌ Карта не найдена", show_alert=True)
                return

            user_card, card = data

            # Сохраняем старые статы
            old_stats = {
                'power': user_card.current_power,
                'health': user_card.current_health,
                'attack': user_card.current_attack,
                'defense': user_card.current_defense,
                'level': user_card.level
            }

            # Рассчитываем стоимость 5 улучшений
            total_cost = 0
            from game.upgrade_calculator import get_upgrade_cost, calculate_stats_for_level
            for i in range(5):
                if user_card.level + i >= 100:
                    break
                total_cost += get_upgrade_cost(card, user_card.level + i)

            if user.dust < total_cost:
                await callback.answer(f"❌ Не хватает пыли! Нужно: {total_cost}", show_alert=True)
                return

            # Применяем улучшения
            upgrades_done = 0
            for _ in range(5):
                if user_card.level >= 100:
                    break
                user.dust -= get_upgrade_cost(card, user_card.level)
                user_card.level += 1
                upgrades_done += 1
                user.total_cards_upgraded += 1

            # Пересчитываем финальные статы
            new_stats = calculate_stats_for_level(card, user_card.level)
            user_card.current_power = new_stats['power']
            user_card.current_health = new_stats['health']
            user_card.current_attack = new_stats['attack']
            user_card.current_defense = new_stats['defense']
            user_card.times_upgraded += upgrades_done

            await session.commit()

            # Разница
            diff_power = user_card.current_power - old_stats['power']
            diff_health = user_card.current_health - old_stats['health']
            diff_attack = user_card.current_attack - old_stats['attack']
            diff_defense = user_card.current_defense - old_stats['defense']

            # Прогресс до бонуса
            next_ten_bonus = ((user_card.level // 10) + 1) * 10
            levels_to_bonus = next_ten_bonus - user_card.level
            ten_level_progress = user_card.level % 10 or 10
            progress_bar = "█" * ten_level_progress + "░" * (10 - ten_level_progress)

            text = f"""
<b>✨ УЛУЧШЕНИЕ КАРТЫ ×{upgrades_done}</b>

<b>{card.card_name}</b> [{card.rarity}]
📈 <b>Уровень:</b> {old_stats['level']} → {user_card.level} (+{upgrades_done})

<b>⚔️ ИЗМЕНЕНИЕ ХАРАКТЕРИСТИК:</b>
💪 Сила:     {old_stats['power']} → {user_card.current_power} (+{diff_power})
❤️ Здоровье: {old_stats['health']} → {user_card.current_health} (+{diff_health})
⚔️ Атака:    {old_stats['attack']} → {user_card.current_attack} (+{diff_attack})
🛡️ Защита:   {old_stats['defense']} → {user_card.current_defense} (+{diff_defense})

<b>📊 ПРОГРЕСС:</b>
Бонус за 10 уровней: +5% ко всем статам
[{progress_bar}] {ten_level_progress}/10
{levels_to_bonus} ур. до следующего бонуса

💰 Потрачено пыли: {total_cost}✨
📦 Осталось пыли: {user.dust}✨
"""

            from bot.keyboards import upgrade_card_keyboard
            keyboard = upgrade_card_keyboard(card_id)

            await callback.message.edit_caption(caption=text, reply_markup=keyboard)
            await callback.answer(f"✨ Карта улучшена {upgrades_done} раз!", show_alert=False)

    except Exception as e:
        logger.exception(f"Ошибка upgrade_5x: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "collection_by_anime")
async def collection_by_anime(callback: types.CallbackQuery):
    """Показать коллекцию, сгруппированную по аниме"""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            # Получаем все карты пользователя с группировкой по аниме
            result = await session.execute(
                select(Card.anime_name, func.count(UserCard.id))
                .join(UserCard, Card.id == UserCard.card_id)
                .where(UserCard.user_id == user.id)
                .group_by(Card.anime_name)
                .order_by(func.count(UserCard.id).desc())
                .limit(20)
            )
            anime_stats = result.all()

            if not anime_stats:
                await callback.message.edit_text(
                    "📭 <b>У вас пока нет карт</b>\n\nОткройте пачку: /open_pack",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="« Назад", callback_data="back_to_collection")]
                    ])
                )
                await callback.answer()
                return

            text = "<b>🎌 КОЛЛЕКЦИЯ ПО АНИМЕ</b>\n\n"
            for anime, count in anime_stats:
                anime_name = anime[:30] + "..." if anime and len(anime) > 30 else (anime or "Без аниме")
                text += f"📺 <b>{anime_name}</b> — {count} карт\n"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="« Назад", callback_data="back_to_collection")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка collection_by_anime: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "collection_favorites")
async def collection_favorites(callback: types.CallbackQuery):
    """Показать избранные карты"""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            result = await session.execute(
                select(UserCard, Card)
                .join(Card, UserCard.card_id == Card.id)
                .where(
                    and_(
                        UserCard.user_id == user.id,
                        UserCard.is_favorite == True
                    )
                )
                .order_by(Card.rarity.desc())
                .limit(20)
            )
            cards = result.all()

            if not cards:
                await callback.message.edit_text(
                    "⭐ <b>У вас нет избранных карт</b>\n\n"
                    "Добавьте карты в избранное при просмотре",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="« Назад", callback_data="back_to_collection")]
                    ])
                )
                await callback.answer()
                return

            text = "<b>⭐ ИЗБРАННЫЕ КАРТЫ</b>\n\n"
            card_ids = []

            for i, (user_card, card) in enumerate(cards[:5], 1):
                text += f"{i}. <b>{card.card_name}</b> [{card.rarity}] Ур.{user_card.level}\n"
                text += f"   💪 {user_card.current_power}\n"
                card_ids.append(user_card.id)

            # Кнопки просмотра
            keyboard = []
            view_row = []
            for idx, cid in enumerate(card_ids, 1):
                view_row.append(InlineKeyboardButton(text=f"🔍 {idx}", callback_data=f"view_card_{cid}"))
            if view_row:
                keyboard.append(view_row)

            keyboard.append([InlineKeyboardButton(text="« Назад", callback_data="back_to_collection")])

            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка collection_favorites: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "collection_in_deck")
async def collection_in_deck(callback: types.CallbackQuery):
    """Показать карты в колоде"""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            result = await session.execute(
                select(UserCard, Card)
                .join(Card, UserCard.card_id == Card.id)
                .where(
                    and_(
                        UserCard.user_id == user.id,
                        UserCard.is_in_deck == True
                    )
                )
                .order_by(Card.rarity.desc())
            )
            cards = result.all()

            if not cards:
                await callback.message.edit_text(
                    "⚔️ <b>В вашей колоде нет карт</b>\n\n"
                    "Добавьте карты в колоду при просмотре",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="« Назад", callback_data="back_to_collection")]
                    ])
                )
                await callback.answer()
                return

            text = "<b>⚔️ КАРТЫ В КОЛОДЕ</b>\n\n"
            for i, (user_card, card) in enumerate(cards, 1):
                text += f"{i}. <b>{card.card_name}</b> [{card.rarity}] Ур.{user_card.level}\n"
                text += f"   💪 {user_card.current_power} | ⚔️ {user_card.current_attack} | 🛡️ {user_card.current_defense}\n\n"

            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="« Назад", callback_data="back_to_collection")]
                ])
            )
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка collection_in_deck: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "collection_stats")
async def collection_stats(callback: types.CallbackQuery):
    """Показать расширенную статистику коллекции"""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            # Общая статистика
            total_cards = user.cards_opened or 0

            # Статистика по редкостям
            rarity_stats = await get_collection_stats(user.id)

            # Подсчет общей силы
            result = await session.execute(
                select(func.sum(UserCard.current_power))
                .where(UserCard.user_id == user.id)
            )
            total_power = result.scalar() or 0

            # Средний уровень
            result = await session.execute(
                select(func.avg(UserCard.level))
                .where(UserCard.user_id == user.id)
            )
            avg_level = result.scalar() or 0

            # ⭐ Избранные
            favorite_count = await session.scalar(
                select(func.count(UserCard.id))
                .where(
                    UserCard.user_id == user.id,
                    UserCard.is_favorite == True
                )
            ) or 0

            # ⚔️ В колоде
            deck_count = await session.scalar(
                select(func.count(UserCard.id))
                .where(
                    UserCard.user_id == user.id,
                    UserCard.is_in_deck == True
                )
            ) or 0


            text = f"""
<b>📊 СТАТИСТИКА КОЛЛЕКЦИИ</b>

<b>📈 Общая информация:</b>
🃏 Всего карт: {total_cards}
📊 Средний уровень: {avg_level:.1f}
💪 Общая сила: {total_power:,}

<b>📋 По редкостям:</b>
🏆 SSS: {rarity_stats.get('SSS', 0)}
✨ ASS: {rarity_stats.get('ASS', 0)}
⭐ S: {rarity_stats.get('S', 0)}
🔮 A: {rarity_stats.get('A', 0)}
💫 B: {rarity_stats.get('B', 0)}
⚡ C: {rarity_stats.get('C', 0)}
🟢 D: {rarity_stats.get('D', 0)}
⚪ E: {rarity_stats.get('E', 0)}

<b>🏆 Прогресс:</b>
📦 Улучшено карт: {user.total_cards_upgraded or 0}
⭐ В избранном: {favorite_count}
⚔️ В колоде: {deck_count}
"""
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="« Назад", callback_data="back_to_collection")]
                ])
            )
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка collection_stats: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "collection_strongest")
async def collection_strongest(callback: types.CallbackQuery):
    """Показать самые сильные карты"""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            result = await session.execute(
                select(UserCard, Card)
                .join(Card, UserCard.card_id == Card.id)
                .where(UserCard.user_id == user.id)
                .order_by(UserCard.current_power.desc())
                .limit(10)
            )
            cards = result.all()

            if not cards:
                await callback.message.edit_text(
                    "📭 <b>У вас пока нет карт</b>",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="« Назад", callback_data="back_to_collection")]
                    ])
                )
                await callback.answer()
                return

            text = "<b>🔝 САМЫЕ СИЛЬНЫЕ КАРТЫ</b>\n\n"
            card_ids = []

            for i, (user_card, card) in enumerate(cards[:5], 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                text += f"{medal} <b>{card.card_name}</b> [{card.rarity}]\n"
                text += f"   💪 Сила: {user_card.current_power} | Ур.{user_card.level}\n"
                card_ids.append(user_card.id)

            # Кнопки просмотра
            keyboard = []
            view_row = []
            for idx, cid in enumerate(card_ids, 1):
                view_row.append(InlineKeyboardButton(text=f"🔍 {idx}", callback_data=f"view_card_{cid}"))
            if view_row:
                keyboard.append(view_row)

            keyboard.append([InlineKeyboardButton(text="« Назад", callback_data="back_to_collection")])

            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка collection_strongest: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# 4. Хендлер просмотра карты (самый общий - ПОСЛЕ всех специфичных)
# 4. Хендлер просмотра карты (самый общий - ПОСЛЕ всех специфичных)
# 4. Хендлер просмотра карты (самый общий - ПОСЛЕ всех специфичных)
# 4. Хендлер просмотра карты (самый общий - ПОСЛЕ всех специфичных)
# 4. Хендлер просмотра карты (самый общий - ПОСЛЕ всех специфичных)


@router.callback_query(F.data.startswith("view_card_"))
async def view_card_detail(callback: types.CallbackQuery):
    """Просмотр детальной информации о карте с изображением"""
    try:
        # Проверяем что это точно view_card_, а не что-то другое
        if not callback.data.startswith("view_card_"):
            return

        card_id = int(callback.data.replace("view_card_", ""))
        logger.info(f"Просмотр карты ID: {card_id}")

        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            result = await session.execute(
                select(UserCard, Card).join(
                    Card,
                    UserCard.card_id == Card.id).where(UserCard.id == card_id))
            data = result.first()

            if not data:
                await callback.answer("Карта не найдена", show_alert=True)
                return

            user_card, card = data

            if user_card.user_id != user.id:
                await callback.answer("Эта карта вам не принадлежит",
                                      show_alert=True)
                return

            # Рассчитываем стоимость улучшения с вашими формулами
            from game.upgrade_calculator import get_upgrade_cost
            upgrade_cost = get_upgrade_cost(card, user_card.level)
            can_upgrade = user_card.level < 100 and user.dust >= upgrade_cost

            # Статистика карты
            text = f"""
<b>✨ {card.card_name}</b>

<b>📋 Информация:</b>
🎭 Персонаж: {card.character_name or 'Неизвестно'}
⭐ Редкость: {card.rarity}
📺 Аниме: {card.anime_name or 'Неизвестно'}

<b>⚔️ Характеристики:</b>
💪 Сила: {user_card.current_power:,}
❤️ Здоровье: {user_card.current_health:,}
⚔️ Атака: {user_card.current_attack:,}
🛡️ Защита: {user_card.current_defense:,}

<b>📊 Прогресс:</b>
📈 Уровень: {user_card.level}/100
✨ Стоимость улучшения: {upgrade_cost} пыли
🔄 Улучшено раз: {user_card.times_upgraded}

<b>🏆 Статус:</b>
{'⚔️ В колоде' if user_card.is_in_deck else '📦 В коллекции'}
{'⭐ Избранная' if user_card.is_favorite else '☆ Не избранная'}
{'🏕️ В экспедиции' if user_card.is_in_expedition else '🏠 Доступна'}

📅 Получена: {user_card.obtained_at.strftime('%d.%m.%Y')}
📊 Прогресс до следующего уровня: {user_card.level + 1}/100
            """

        from bot.keyboards import card_detail_keyboard
        keyboard = card_detail_keyboard(card_id=card_id,
                                        is_favorite=user_card.is_favorite,
                                        is_in_deck=user_card.is_in_deck,
                                        can_upgrade=can_upgrade,
                                        upgrade_cost=upgrade_cost,
                                        user_dust=user.dust)

        try: 
            # Обновляем существующее сообщение
            await callback.message.edit_media(
                media=types.InputMediaPhoto(
                    media=card.original_url,
                    caption=text
                ),
                reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение: {e}")
            # Если не получилось — отправляем новое
            await callback.message.answer_photo(
                photo=card.original_url,
                caption=text,
                reply_markup=keyboard
            )

        await callback.answer()    

    except Exception as e:
        logger.exception(f"Ошибка view_card_detail: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# 5. Навигационные хендлеры


@router.callback_query(F.data == "back_to_main", StateFilter("*"))
async def cb_back_main(callback: CallbackQuery):
    try:
        await callback.message.edit_text("🏠 Главное меню",
                                         reply_markup=main_menu_keyboard())
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка cb_back_main: {e}")
        await callback.answer("❌ Произошла ошибка.")


@router.callback_query(F.data == "back_to_collection_menu")
async def cb_back_collection(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "🃏 Коллекция", reply_markup=collection_menu_keyboard())
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка cb_back_collection: {e}")
        await callback.answer("❌ Произошла ошибка.")
