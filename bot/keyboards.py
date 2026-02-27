# bot/keyboards.py
from aiogram import Bot
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models.card import Card
from database.models.user_card import UserCard
from typing import List, Tuple
from datetime import datetime


async def set_bot_commands(bot: Bot):
    """Установка команд бота в меню"""
    commands = [
        BotCommand(command="/start", description="🏠 Главное меню"),
        BotCommand(command="/profile", description="📊 Профиль"),
        BotCommand(command="/collection", description="🃏 Коллекция"),
        BotCommand(command="/open_pack", description="📦 Открыть пачку"),
        BotCommand(command="/expedition", description="🏕️ Экспедиции"),
        BotCommand(command="/daily", description="🎁 Дейлик"),
        BotCommand(command="/arena", description="⚔️ Арена"),
        BotCommand(command="/quiz", description="🤓 Викторина"),
        BotCommand(command="/help", description="❓ Помощь"),
    ]
    await bot.set_my_commands(commands)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 Открыть пачку", callback_data="open_pack"),
        InlineKeyboardButton(text="🃏 Коллекция", callback_data="back_to_collection"),
    )
    builder.row(
        InlineKeyboardButton(text="⚔️ Арена", callback_data="open_arena"),
        InlineKeyboardButton(text="🏕️ Экспедиции", callback_data="expedition"),
    )
    builder.row(
        InlineKeyboardButton(text="🎯 Викторина", callback_data="quiz_menu"),
    )
    return builder.as_markup()


def collection_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню коллекции"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📊 По редкости", callback_data="collection_by_rarity"
        ),
        InlineKeyboardButton(text="🎌 По аниме", callback_data="collection_by_anime"),
    )
    builder.row(
        InlineKeyboardButton(text="⭐ Избранные", callback_data="collection_favorites"),
        InlineKeyboardButton(text="⚔️ В колоде", callback_data="collection_in_deck"),
    )
    builder.row(
        InlineKeyboardButton(text="📈 Статистика", callback_data="collection_stats"),
        InlineKeyboardButton(
            text="🔝 Самые\n сильные", callback_data="collection_strongest"
        ),
    )
    return builder.as_markup()


def rarity_keyboard() -> InlineKeyboardMarkup:
    """Выбор редкости"""
    builder = InlineKeyboardBuilder()
    rarities = ["SSS", "ASS", "S", "A", "B", "C", "D", "E"]
    emoji = ["🏆", "✨", "⭐", "🔮", "💫", "⚡", "🟢", "⚪"]

    for rarity, emj in zip(rarities, emoji):
        builder.add(
            InlineKeyboardButton(
                text=f"{emj} {rarity}", callback_data=f"rarity_{rarity}"
            )
        )

    builder.adjust(4, 4)
    builder.row(
        InlineKeyboardButton(text="« Назад", callback_data="back_to_collection_menu")
    )
    return builder.as_markup()


def collection_keyboard(
    page: int, has_next: bool, rarity: str = None
) -> InlineKeyboardMarkup:
    """Клавиатура для пагинации коллекции с изображениями"""
    buttons = []

    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=(
                    f"col_page:{page-1}:{rarity}" if rarity else f"col_page:{page-1}"
                ),
            )
        )
    if has_next:
        nav_row.append(
            InlineKeyboardButton(
                text="➡️ Вперёд",
                callback_data=(
                    f"col_page:{page+1}:{rarity}" if rarity else f"col_page:{page+1}"
                ),
            )
        )

    if nav_row:
        buttons.append(nav_row)

    buttons.append(
        [
            InlineKeyboardButton(
                text="« К редкостям", callback_data="collection_by_rarity"
            ),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def expedition_main_keyboard(
    active_count: int, uncollected_count: int, slots: int, free_slots: int
) -> InlineKeyboardMarkup:
    """Главное меню экспедиций"""
    builder = InlineKeyboardBuilder()

    if uncollected_count > 0:
        builder.row(
            InlineKeyboardButton(
                text=f"🎁 ЗАБРАТЬ НАГРАДЫ ({uncollected_count})",
                callback_data="exped_claim_all",
            )
        )

    if free_slots > 0:
        builder.row(
            InlineKeyboardButton(text="🕐 30 мин", callback_data="exped_new_short"),
            InlineKeyboardButton(text="🕑 2 часа", callback_data="exped_new_medium"),
        )
        builder.row(
            InlineKeyboardButton(text="🕕 6 часов", callback_data="exped_new_long"),
        )

    builder.row(
        InlineKeyboardButton(
            text=f"📋 Мои экспедиции ({active_count}/{slots})",
            callback_data="exped_list",
        )
    )

    builder.row(InlineKeyboardButton(text="« Назад", callback_data="back_to_main"))

    return builder.as_markup()


def expedition_cards_keyboard(
    cards: List[Tuple[UserCard, Card]], selected_ids: List[int]
) -> InlineKeyboardMarkup:
    """Клавиатура выбора карт для экспедиции"""
    builder = InlineKeyboardBuilder()

    for user_card, card in cards[:20]:  # Максимум 20 карт
        card_id = user_card.id
        is_selected = card_id in selected_ids

        # Эмодзи статуса
        status = "✅ " if is_selected else ""

        # Обрезаем длинные названия
        card_name = (
            card.card_name[:20] + "..." if len(card.card_name) > 20 else card.card_name
        )

        builder.row(
            InlineKeyboardButton(
                text=f"{status}{card_name} [{card.rarity}] Ур.{user_card.level}",
                callback_data=f"exped_select_{card_id}",
            )
        )

    # Кнопки управления
    control_buttons = []

    if len(selected_ids) > 0:
        control_buttons.append(
            InlineKeyboardButton(
                text=f"✅ Подтвердить ({len(selected_ids)} карт)",
                callback_data="exped_confirm_cards",
            )
        )

    control_buttons.append(
        InlineKeyboardButton(text="❌ Отмена", callback_data="exped_cancel")
    )

    builder.row(*control_buttons)

    # Информация
    builder.row(
        InlineKeyboardButton(
            text="ℹ️ Можно выбрать 1-3 карты | Бонус за 2+ карт из 1 аниме +50%",
            callback_data="noop",
        )
    )

    return builder.as_markup()


def expedition_confirm_keyboard(duration: str, card_count: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения экспедиции"""
    builder = InlineKeyboardBuilder()

    # duration_names = {
    #     "short": "🕐 30 мин",
    #     "medium": "🕑 2 часа",
    #     "long": "🕕 6 часов"
    # }

    builder.row(
        InlineKeyboardButton(
            text="✅ Отправить в экспедицию", callback_data=f"exped_start_{duration}"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="◀️ Назад к выбору карт", callback_data="exped_back_to_cards"
        ),
        InlineKeyboardButton(text="❌ Отмена", callback_data="exped_cancel"),
    )

    return builder.as_markup()


def expedition_list_keyboard(
    expeditions: List, uncollected_count: int
) -> InlineKeyboardMarkup:
    """Клавиатура списка экспедиций"""
    builder = InlineKeyboardBuilder()

    now = datetime.now()

    for exp in expeditions[:5]:  # Максимум 5
        if exp.status == "ACTIVE":
            time_left = exp.ends_at - now
            minutes_left = int(time_left.total_seconds() / 60)
            status = f"⏳ {minutes_left} мин"
        else:
            status = "Продолжается.. ⏳"

        builder.row(
            InlineKeyboardButton(
                text=f"{exp.name[:20]}... - {status}",
                callback_data=f"exped_info_{exp.id}",
            )
        )

    if uncollected_count > 0:
        builder.row(
            InlineKeyboardButton(
                text=f"🎁 Забрать все ({uncollected_count})",
                callback_data="exped_claim_all",
            )
        )

    builder.row(InlineKeyboardButton(text="« Назад", callback_data="expedition"))

    return builder.as_markup()


def card_detail_keyboard(
    card_id: int,
    is_favorite: bool,
    is_in_deck: bool,
    can_upgrade: bool,
    upgrade_cost: int = None,
    user_dust: int = None,
) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра карты"""
    builder = InlineKeyboardBuilder()

    # Статусы
    favorite_text = "⭐ Убрать" if is_favorite else "⭐ В избранное"
    deck_text = "⚔️ Убрать из колоды" if is_in_deck else "⚔️ В колоду"

    builder.row(
        InlineKeyboardButton(text=favorite_text, callback_data=f"favorite_{card_id}"),
        InlineKeyboardButton(text=deck_text, callback_data=f"deck_{card_id}"),
    )

    # Кнопка улучшения
    if can_upgrade and upgrade_cost:
        builder.row(
            InlineKeyboardButton(
                text=f"✨ Улучшить ({upgrade_cost}✨ (у вас {user_dust} пыли ✨))",
                callback_data=f"upgrade_{card_id}",
            )
        )
    elif upgrade_cost and user_dust is not None:
        builder.row(
            InlineKeyboardButton(
                text=f"✨ Не хватает ({user_dust}/{upgrade_cost}✨)",
                callback_data="noop",
            )
        )

    # Навигация
    builder.row(
        InlineKeyboardButton(
            text="« Назад в коллекцию", callback_data="back_to_collection"
        )
    )

    return builder.as_markup()


def upgrade_card_keyboard(card_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Ещё +1", callback_data=f"upgrade_{card_id}"
                ),
                InlineKeyboardButton(
                    text="✖️ ×5", callback_data=f"5x_upgrade_{card_id}"
                ),
            ],
            [
                # InlineKeyboardButton(text="🎯 До бонуса", callback_data=f"upgrade_to_bonus_{card_id}"),
                InlineKeyboardButton(
                    text="◀️ Назад", callback_data=f"view_card_{card_id}"
                )
            ],
        ]
    )


def quiz_start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для начала викторины"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎯 НАЧАТЬ ВИКТОРИНУ", callback_data="quiz_start")
    )
    builder.row(
        InlineKeyboardButton(text="« Назад", callback_data="back_to_main")
    )
    return builder.as_markup()


def quiz_options_keyboard(options: List[str], question_index: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура с вариантами ответа для вопроса"""
    builder = InlineKeyboardBuilder()

    # Добавляем варианты ответа (по 1 в ряд для компактности)
    for i, option in enumerate(options):
        # ✅ ИСПРАВЛЕНО: Интеллектуальное обрезание с сохранением читаемости
        if len(option) > 25:
            # Разбиваем длинное название на части
            words = option.split()
            if len(words) > 1:
                # Берем первые 2-3 слова
                shortened = " ".join(words[:2])
                if len(shortened) > 20:
                    shortened = shortened[:18] + "…"
            else:
                # Если одно слово - обрезаем по символам
                shortened = option[:20] + "…"
        else:
            shortened = option

        # Добавляем эмодзи для наглядности (по желанию)
        emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"][i] if i < 4 else f"{i+1}."

        builder.add(
            InlineKeyboardButton(
                text=f"{emoji} {shortened}",
                callback_data=f"quiz_answer_{i}"
            )
        )

    builder.adjust(1)  # По 1 кнопки в ряд

    # Добавляем информацию о прогрессе
    builder.row(
        InlineKeyboardButton(
            text=f"❓ Вопрос {question_index + 1}/{total}",
            callback_data="noop"
        )
    )

    return builder.as_markup()


def quiz_continue_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для продолжения после ответа"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➡️ ДАЛЬШЕ", callback_data="quiz_next")
    )
    return builder.as_markup()


def quiz_result_keyboard(correct_answers: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура после завершения викторины"""
    builder = InlineKeyboardBuilder()

    if correct_answers == total:
        builder.row(
            InlineKeyboardButton(text="🎉 ЕЩЁ РАЗ (через час)", callback_data="quiz_again_locked")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🔄 ПОПРОБОВАТЬ СНОВА", callback_data="quiz_restart")
        )

    builder.row(
        InlineKeyboardButton(text="🏠 В ГЛАВНОЕ МЕНЮ", callback_data="back_to_main")
    )

    return builder.as_markup()
