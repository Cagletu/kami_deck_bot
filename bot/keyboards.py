# bot/keyboards.py
from aiogram import Bot
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models.card import Card
from database.models.user_card import UserCard
from typing import List, Tuple

async def set_bot_commands(bot: Bot):
    """Установка команд бота в меню"""
    commands = [
        BotCommand(command="/start", description="🏠 Главное меню"),
        BotCommand(command="/profile", description="📊 Профиль"),
        BotCommand(command="/collection", description="🃏 Коллекция"),
        BotCommand(command="/open_pack", description="📦 Открыть пачку"),
        BotCommand(command="/expedition", description="🏕️ Экспедиции"),
        BotCommand(command="/daily", description="🎁 Дейлик"),
        BotCommand(command="/help", description="❓ Помощь"),
    ]
    await bot.set_my_commands(commands)

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🃏 Коллекция", callback_data="collection_by_rarity"),
        InlineKeyboardButton(text="📊 Профиль", callback_data="profile"),
    )
    builder.row(
        InlineKeyboardButton(text="📦 Открыть пачку", callback_data="open_pack"),
        InlineKeyboardButton(text="🏕️ Экспедиции", callback_data="expedition"),
    )
    return builder.as_markup()

def collection_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню коллекции"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 По редкости", callback_data="collection_by_rarity"),
        InlineKeyboardButton(text="🎌 По аниме нераб", callback_data="collection_by_anime"),
    )
    builder.row(
        InlineKeyboardButton(text="⭐ Избранные нераб", callback_data="collection_favorites"),
        InlineKeyboardButton(text="⚔️ В колоде нераб", callback_data="collection_in_deck"),
    )
    builder.row(
        InlineKeyboardButton(text="📈 Статистика", callback_data="collection_stats"),
        InlineKeyboardButton(text="🔝 Самые сильные нераб", callback_data="collection_strongest"),
    )
    return builder.as_markup()

def rarity_keyboard() -> InlineKeyboardMarkup:
    """Выбор редкости"""
    builder = InlineKeyboardBuilder()
    rarities = ["SSS", "ASS", "S", "A", "B", "C", "D", "E"]
    emoji = ["🏆", "✨", "⭐", "🔮", "💫", "⚡", "🟢", "⚪"]

    for rarity, emj in zip(rarities, emoji):
        builder.add(InlineKeyboardButton(
            text=f"{emj} {rarity}",
            callback_data=f"rarity_{rarity}"
        ))

    builder.adjust(4, 4)
    builder.row(
        InlineKeyboardButton(text="« Назад", callback_data="back_to_collection_menu")
    )
    return builder.as_markup()


def collection_keyboard(page: int, has_next: bool, rarity: str = None) -> InlineKeyboardMarkup:
    """Клавиатура для пагинации коллекции с изображениями"""
    buttons = []

    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Назад", 
                callback_data=f"col_page:{page-1}:{rarity}" if rarity else f"col_page:{page-1}"
            )
        )
    if has_next:
        nav_row.append(
            InlineKeyboardButton(
                text="➡️ Вперёд", 
                callback_data=f"col_page:{page+1}:{rarity}" if rarity else f"col_page:{page+1}"
            )
        )

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="« К редкостям", callback_data="collection_by_rarity"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def expedition_main_keyboard(active_count: int, uncollected_count: int, slots: int, free_slots: int) -> InlineKeyboardMarkup:
    """Главное меню экспедиций"""
    builder = InlineKeyboardBuilder()

    if uncollected_count > 0:
        builder.row(
            InlineKeyboardButton(
                text=f"🎁 ЗАБРАТЬ НАГРАДЫ ({uncollected_count})",
                callback_data="exped_claim_all"
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
            callback_data="exped_list"
        )
    )

    builder.row(
        InlineKeyboardButton(text="« Назад", callback_data="back_to_main")
    )

    return builder.as_markup()


def expedition_cards_keyboard(cards: List[Tuple[UserCard, Card]], selected_ids: List[int]) -> InlineKeyboardMarkup:
    """Клавиатура выбора карт для экспедиции"""
    builder = InlineKeyboardBuilder()

    for user_card, card in cards[:9]:  # Максимум 9 карт
        card_id = user_card.id
        is_selected = card_id in selected_ids

        # Эмодзи статуса
        status = "✅ " if is_selected else ""

        builder.row(
            InlineKeyboardButton(
                text=f"{status}{card.card_name} [{card.rarity}] Ур.{user_card.level}",
                callback_data=f"exped_select_{card_id}"
            )
        )

    # Кнопки управления
    control_buttons = []

    if len(selected_ids) > 0:
        control_buttons.append(
            InlineKeyboardButton(
                text=f"✅ Подтвердить ({len(selected_ids)} карт)",
                callback_data="exped_confirm_cards"
            )
        )

    control_buttons.append(
        InlineKeyboardButton(text="❌ Отмена", callback_data="exped_cancel")
    )

    builder.row(*control_buttons)

    # Информация
    builder.row(
        InlineKeyboardButton(
            text="ℹ️ Можно выбрать 1-3 карты",
            callback_data="noop"
        )
    )

    return builder.as_markup()


def expedition_confirm_keyboard(duration: str, card_count: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения экспедиции"""
    builder = InlineKeyboardBuilder()

    duration_names = {
        "short": "🕐 30 мин",
        "medium": "🕑 2 часа",
        "long": "🕕 6 часов"
    }

    builder.row(
        InlineKeyboardButton(
            text="✅ Отправить в экспедицию",
            callback_data=f"exped_start_{duration}"
        )
    )

    builder.row(
        InlineKeyboardButton(text="◀️ Назад к выбору карт", callback_data="exped_back_to_cards"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="exped_cancel")
    )

    return builder.as_markup()


def expedition_list_keyboard(expeditions: List, uncollected_count: int) -> InlineKeyboardMarkup:
    """Клавиатура списка экспедиций"""
    builder = InlineKeyboardBuilder()

    now = datetime.now()

    for exp in expeditions[:5]:  # Максимум 5
        if exp.status == "ACTIVE":
            time_left = exp.ends_at - now
            minutes_left = int(time_left.total_seconds() / 60)
            status = f"⏳ {minutes_left} мин"
        else:
            status = "✅ Готово!"

        builder.row(
            InlineKeyboardButton(
                text=f"{exp.name[:20]}... - {status}",
                callback_data=f"exped_info_{exp.id}"
            )
        )

    if uncollected_count > 0:
        builder.row(
            InlineKeyboardButton(
                text=f"🎁 Забрать все ({uncollected_count})",
                callback_data="exped_claim_all"
            )
        )

    builder.row(
        InlineKeyboardButton(text="« Назад", callback_data="expedition")
    )

    return builder.as_markup()
    