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
from sqlalchemy import func, and_

from sqlalchemy import select

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

router = Router()
logger = logging.getLogger(__name__)

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
        await message.answer(collection_text, reply_markup=collection_menu_keyboard())

    except Exception as e:
        logger.exception(f"Ошибка в хендлере cmd_collection: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


# Callback для редкости и возврата
@router.callback_query(F.data == "collection_by_rarity")
async def collection_by_rarity(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            "<b>Выберите редкость для просмотра:</b>",
            reply_markup=rarity_keyboard()
        )
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
                rarity_filter=rarity
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
            nav_buttons.append(InlineKeyboardButton(
                text="◀️", 
                callback_data=f"rarity_{rarity}_{page-1}"
            ))

        nav_buttons.append(InlineKeyboardButton(
            text=f"{page}/{total_pages}", 
            callback_data="noop"
        ))

        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(
                text="▶️", 
                callback_data=f"rarity_{rarity}_{page+1}"
            ))

        keyboard.append(nav_buttons)

        # Кнопки просмотра карт (максимум 5)
        view_row = []
        for idx, card_id in enumerate(card_ids[:5], 1):
            view_row.append(InlineKeyboardButton(
                text=f"🔍 {idx}", 
                callback_data=f"view_card_{card_id}"
            ))
        if view_row:
            keyboard.append(view_row)

        # Кнопки навигации по меню
        keyboard.append([
            InlineKeyboardButton(text="« К редкостям", callback_data="collection_by_rarity"),
            InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_collection")
        ])

        await callback.message.edit_text(
            text, 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
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

            cards, pack_open = await open_pack(user.id, "common", session)
            await session.commit()

            # Обновляем данные пользователя после коммита
            await session.refresh(user)

        text = f"<b>📦 ВЫ ОТКРЫЛИ ПАЧКУ КАРТ!</b>\n\n💰 Потрачено: <code>100</code> монет\n💰 Осталось: <code>{user.coins}</code> монет\n\n<b>🎉 Вы получили:</b>\n"
        for card in cards:
            emoji = {'E':'⚪','D':'🟢','C':'⚡','B':'💫','A':'🔮','S':'⭐','ASS':'✨','SSS':'🏆'}.get(card.rarity,'🃏')
            text += f"{emoji} <b>{card.card_name}</b> [{card.rarity}]\n"
        if pack_open.guaranteed_rarity:
            text += f"\n🎁 <b>ГАРАНТИЯ!</b> Вам выпала {pack_open.guaranteed_rarity} карта!"

        await message.answer_photo(photo=cards[0].original_url, caption=text)

        if len(cards) > 1:
            media_group = [
                types.InputMediaPhoto(
                    media=card.original_url, 
                    caption=f"{card.card_name} [{card.rarity}]"
                ) 
                for card in cards[1:]
            ]
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

            if user.last_daily_tasks and user.last_daily_tasks.date() == datetime.now().date():
                await message.answer("❌ Вы уже получили ежедневную награду сегодня!\nЗаходите завтра в 00:00 по МСК")
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


@router.callback_query(F.data.startswith("view_card_"))
async def view_card_detail(callback: types.CallbackQuery):
    """Просмотр детальной информации о карте с изображением"""
    try:
        card_id = int(callback.data.replace("view_card_", ""))

        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

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
                await callback.answer("Эта карта вам не принадлежит", show_alert=True)
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
        keyboard = card_detail_keyboard(
            card_id=card_id,
            is_favorite=user_card.is_favorite,
            is_in_deck=user_card.is_in_deck,
            can_upgrade=can_upgrade,
            upgrade_cost=upgrade_cost,
            user_dust=user.dust
        )

        await callback.message.answer_photo(
            photo=card.original_url,
            caption=text,
            reply_markup=keyboard
        )
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка view_card_detail: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# ===== CALLBACKS =====

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

            cards, pack_open = await open_pack(user.id, "common", session)
            await session.commit()
            await session.refresh(user)

        text = f"<b>📦 ВЫ ОТКРЫЛИ ПАЧКУ КАРТ!</b>\n\n💰 Потрачено: <code>100</code> монет\n💰 Осталось: <code>{user.coins}</code> монет\n\n<b>🎉 Вы получили:</b>\n"
        for card in cards:
            emoji = {'E':'⚪','D':'🟢','C':'⚡','B':'💫','A':'🔮','S':'⭐','ASS':'✨','SSS':'🏆'}.get(card.rarity,'🃏')
            text += f"{emoji} <b>{card.card_name}</b> [{card.rarity}]\n"
        if pack_open.guaranteed_rarity:
            text += f"\n🎁 <b>ГАРАНТ!</b> Вам выпала {pack_open.guaranteed_rarity} карта!"

        await callback.message.answer_photo(photo=cards[0].original_url, caption=text)

        if len(cards) > 1:
            media_group = [
                types.InputMediaPhoto(
                    media=card.original_url,
                    caption=f"{card.card_name} [{card.rarity}]"
                )
                for card in cards[1:]
            ]
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
            cards, has_next = await get_user_cards_paginated(
                session=session,
                user_id=user.id,
                page=page,
                rarity=rarity
            )

        if not cards:
            await callback.answer("Больше карт нет")
            return

        card = cards[0]

        caption = (
            f"🃏 <b>{card.card.card_name}</b>\n"
            f"⭐ {card.card.rarity}\n"
            f"⚔️ {card.current_power}"
        )

        await callback.message.edit_media(
            media=types.InputMediaPhoto(
                media=card.card.original_url,
                caption=caption
            ),
            reply_markup=collection_keyboard(page, has_next, rarity)
        )

        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка cb_collection_page: {e}")
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


@router.callback_query(F.data == "back_to_main", StateFilter("*"))
async def cb_back_main(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "🏠 Главное меню",
            reply_markup=main_menu_keyboard()
        )
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка cb_back_main: {e}")
        await callback.answer("❌ Произошла ошибка.")


@router.callback_query(F.data == "back_to_collection_menu")
async def cb_back_collection(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "🃏 Коллекция",
            reply_markup=collection_menu_keyboard()
        )
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка cb_back_collection: {e}")
        await callback.answer("❌ Произошла ошибка.")


@router.message(Command("cancel"), StateFilter("*"))
async def cancel_any(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено")


@router.callback_query(F.data.startswith("favorite_"))
async def toggle_favorite_card(callback: types.CallbackQuery):
    """Добавить/убрать карту из избранного"""
    try:
        card_id = int(callback.data.replace("favorite_", ""))

        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            result = await session.execute(
                select(UserCard)
                .where(
                    and_(
                        UserCard.id == card_id,
                        UserCard.user_id == user.id
                    )
                )
            )
            user_card = result.scalar_one_or_none()

            if not user_card:
                await callback.answer("Карта не найдена", show_alert=True)
                return

            user_card.is_favorite = not user_card.is_favorite
            await session.commit()

            status = "⭐ добавлена в избранное" if user_card.is_favorite else "☆ убрана из избранного"
            await callback.answer(f"Карта {status}!")

            # Обновляем сообщение
            await view_card_detail(callback)

    except Exception as e:
        logger.exception(f"Ошибка toggle_favorite_card: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("deck_"))
async def toggle_deck_card(callback: types.CallbackQuery):
    """Добавить/убрать карту из колоды"""
    try:
        card_id = int(callback.data.replace("deck_", ""))

        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

            # Проверяем сколько карт уже в колоде
            deck_count = await session.execute(
                select(func.count())
                .select_from(UserCard)
                .where(
                    and_(
                        UserCard.user_id == user.id,
                        UserCard.is_in_deck == True
                    )
                )
            )
            deck_count = deck_count.scalar()

            result = await session.execute(
                select(UserCard)
                .where(
                    and_(
                        UserCard.id == card_id,
                        UserCard.user_id == user.id
                    )
                )
            )
            user_card = result.scalar_one_or_none()

            if not user_card:
                await callback.answer("Карта не найдена", show_alert=True)
                return

            # Если добавляем в колоду, проверяем лимит
            if not user_card.is_in_deck and deck_count >= 5:
                await callback.answer("❌ В колоде может быть только 5 карт!", show_alert=True)
                return

            user_card.is_in_deck = not user_card.is_in_deck
            await session.commit()

            status = "⚔️ добавлена в колоду" if user_card.is_in_deck else "📦 убрана из колоды"
            await callback.answer(f"Карта {status}!")

            # Обновляем сообщение
            await view_card_detail(callback)

    except Exception as e:
        logger.exception(f"Ошибка toggle_deck_card: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("upgrade_"))
async def upgrade_card(callback: types.CallbackQuery):
    """Улучшить карту"""
    try:
        card_id = int(callback.data.replace("upgrade_", ""))

        async with AsyncSessionLocal() as session:
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
            user = await session.get(User, callback.from_user.id)

            if user_card.user_id != user.id:
                await callback.answer("Карта не принадлежит вам", show_alert=True)
                return

            # Проверка уровня
            if user_card.level >= 100:
                await callback.answer("Карта уже максимального уровня!", show_alert=True)
                return

            # Расчет стоимости
            from game.upgrade_calculator import get_upgrade_cost
            upgrade_cost = get_upgrade_cost(card, user_card.level)

            if user.dust < upgrade_cost:
                await callback.answer(f"❌ Не хватает пыли! Нужно: {upgrade_cost}", show_alert=True)
                return

            # Улучшаем
            user.dust -= upgrade_cost
            user_card.level += 1
            user_card.times_upgraded += 1

            # Пересчитываем характеристики
            from game.upgrade_calculator import calculate_stats_for_level
            new_stats = calculate_stats_for_level(card, user_card.level)

            user_card.current_power = new_stats['power']
            user_card.current_health = new_stats['health']
            user_card.current_attack = new_stats['attack']
            user_card.current_defense = new_stats['defense']

            await session.commit()

            await callback.answer(f"✨ Карта улучшена до {user_card.level} уровня!", show_alert=False)

            # Обновляем отображение
            await view_card_detail(callback)

    except Exception as e:
        logger.exception(f"Ошибка upgrade_card: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)