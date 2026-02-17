from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import logging
import json


router = Router()
logger = logging.getLogger(__name__)

# URL для WebApp (уже в корне)
WEBAPP_URL = "https://kamideckbot-production.up.railway.app/arena.html"

@router.callback_query(F.data == "arena_battle")
async def start_arena(callback: types.CallbackQuery):
    """Обработчик кнопки начала битвы на арене"""
    try:
        # Создаем клавиатуру с WebApp кнопкой
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⚔️ НАЧАТЬ БИТВУ",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
        ])

        # Отправляем/обновляем сообщение
        await callback.message.edit_text(
            "⚔️ <b>АРЕНА</b>\n\n"
            "Нажмите кнопку чтобы открыть арену и сразиться с противником!\n\n"
            "💡 <b>Как играть:</b>\n"
            "• Выбирайте карты для атаки\n"
            "• Используйте АВТОБОЙ для быстрого боя\n"
            "• Победа приносит рейтинг и награды",
            reply_markup=keyboard
        )
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка в start_arena: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    """Обрабатывает данные из WebApp"""
    try:
        data = json.loads(message.web_app_data.data)
        logger.info(f"Получены данные из WebApp: {data}")

        # Здесь можно обработать результаты боя
        action = data.get('action')

        if action == 'battle_result':
            result = data.get('result')
            if result == 'win':
                await message.answer("🎉 Поздравляем с победой!")
            elif result == 'lose':
                await message.answer("😔 В следующий раз повезет!")

    except Exception as e:
        logger.exception(f"Ошибка обработки WebApp данных: {e}")
        