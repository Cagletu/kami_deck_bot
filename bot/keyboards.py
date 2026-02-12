# bot/keyboards.py
from aiogram import Bot
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
        InlineKeyboardButton(text="🎌 По аниме", callback_data="collection_by_anime"),
    )
    builder.row(
        InlineKeyboardButton(text="⭐ Избранные", callback_data="collection_favorites"),
        InlineKeyboardButton(text="⚔️ В колоде", callback_data="collection_in_deck"),
    )
    builder.row(
        InlineKeyboardButton(text="📈 Статистика", callback_data="collection_stats"),
        InlineKeyboardButton(text="🔝 Самые сильные", callback_data="collection_strongest"),
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

def expedition_type_keyboard() -> InlineKeyboardMarkup:
    """Выбор типа экспедиции"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🕐 30 мин", callback_data="expedition_short"),
        InlineKeyboardButton(text="🕑 2 часа", callback_data="expedition_medium"),
    )
    builder.row(
        InlineKeyboardButton(text="🕕 6 часов", callback_data="expedition_long"),
        InlineKeyboardButton(text="« Назад", callback_data="back_to_main"),
    )
    return builder.as_markup()


def collection_keyboard(page: int, has_next: bool):
    buttons = []

    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"col_page:{page-1}")
        )
    if has_next:
        nav_row.append(
            InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"col_page:{page+1}")
        )

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="🔎 Поиск", callback_data="col_search"),
        InlineKeyboardButton(text="🎴 Фильтр", callback_data="col_filter"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
    