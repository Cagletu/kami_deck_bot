from aiogram import Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import logging

from database.base import AsyncSessionLocal
from database.crud import get_user_or_create
from database.models.user import User
from game.expedition_system import ExpeditionManager
from bot.states import ExpeditionStates
from bot.keyboards import (
    expedition_main_keyboard,
    expedition_cards_keyboard,
    expedition_confirm_keyboard,
    expedition_list_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("expedition"))
async def cmd_expedition(message: Message):
    """Главное меню экспедиций"""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, message.from_user.id)

        active, uncollected = await ExpeditionManager.get_active_expeditions(session, user.id)
        await session.commit()
        
        free_slots = user.expeditions_slots - len(active)

        text = f"""
<b>🏕️ ЭКСПЕДИЦИИ</b>

📊 <b>Ваши слоты:</b> {user.expeditions_slots}
🔵 Активных: {len(active)}
🟢 Готово к забору: {len(uncollected)}
⚪ Свободно: {free_slots}

<b>⚡ Доступные экспедиции:</b>

🕐 <b>30 минут</b>
• {6 * 1}-{9 * 1} монет за карту
• {1 * 1} пыли за карту
• 50% шанс на E карту

🕑 <b>2 часа</b>
• {24 * 1}-{36 * 1} монет за карту
• {4 * 1} пыли за карту
• 100% шанс на D карту

🕕 <b>6 часов</b>
• {72 * 1}-{108 * 1} монет за карту
• {12 * 1} пыли за карту
• 100% шанс на C карту

💡 <b>Бонусы:</b>
• +50% награды за карты из одного аниме
• x1-x3 за количество карт
"""
        await message.answer(
            text,
            reply_markup=expedition_main_keyboard(
                len(active), 
                len(uncollected), 
                user.expeditions_slots,
                free_slots
            )
        )

    except Exception as e:
        logger.exception(f"Ошибка cmd_expedition: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "expedition", StateFilter("*"))
async def exped_main_menu(callback: CallbackQuery):
    """Возврат в главное меню экспедиций"""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_or_create(session, callback.from_user.id)

        active, uncollected = await ExpeditionManager.get_active_expeditions(session, user.id)
        await session.commit()
        
        free_slots = user.expeditions_slots - len(active)

        text = f"""
<b>🏕️ ЭКСПЕДИЦИИ</b>

📊 <b>Ваши слоты:</b> {user.expeditions_slots}
🔵 Активных: {len(active)}
🟢 Готово к забору: {len(uncollected)}
⚪ Свободно: {free_slots}

<b>⚡ Доступные экспедиции:</b>

🕐 <b>30 минут</b>
• 6-9 монет за карту
• 1 пыль за карту
• 50% шанс на E карту

🕑 <b>2 часа</b>
• 24-36 монет за карту
• 4 пыли за карту
• 100% шанс на D карту

🕕 <b>6 часов</b>
• 72-108 монет за карту
• 12 пыли за карту
• 100% шанс на C карту

💡 <b>Бонусы:</b>
• +50% награды за карты из одного аниме
• x1-x3 за количество карт
"""
        await callback.message.edit_text(
            text,
            reply_markup=expedition_main_keyboard(
                len(active), 
                len(uncollected), 
                user.expeditions_slots,
                free_slots
            )
        )
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка exped_main_menu: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("exped_new_"))
async def exped_new_start(callback: CallbackQuery, state: FSMContext):
    """Начало новой экспедиции - выбор карт"""
    try:
        duration = callback.data.replace("exped_new_", "")  # short, medium, long

        # Сохраняем длительность
        await state.update_data(duration=duration)
        await state.update_data(selected_cards=[])
        await state.set_state(ExpeditionStates.choosing_cards)

        # Показываем доступные карты
        async with AsyncSessionLocal() as session:
            cards = await ExpeditionManager.get_available_cards(session, callback.from_user.id)

            # 🔍 ДОБАВЛЯЕМ ОТЛАДКУ
            logger.info(f"Найдено доступных карт: {len(cards)}")
            if cards:
                for user_card, card in cards[:3]:
                    logger.info(f"  - Карта: {card.card_name} [{card.rarity}], Ур.{user_card.level}, ID: {user_card.id}")
                    logger.info(f"    is_in_deck: {user_card.is_in_deck}, is_in_expedition: {user_card.is_in_expedition}")
    
            if not cards:
                await callback.message.edit_text(
                    "❌ <b>Нет карт для экспедиции!</b>\n\n"
                    "Карты должны быть:\n"
                    "• Не в колоде\n"
                    "• Не в другой экспедиции\n\n"
                    "Откройте пачку: /open_pack",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="« Назад", callback_data="expedition")]
                    ])
                )
                await callback.answer()
                return
    
            # Получаем количество карт для отображения
            card_count = len(cards)
    
            text = f"""
    <b>🏕️ ВЫБЕРИТЕ КАРТЫ</b>
    
    📊 Доступно карт: {card_count}
    Можно выбрать от 1 до 3 карт.
    ✅ - карта выбрана
    
    💡 <b>Бонус +50%</b> если все карты из одного аниме!
    """
            await callback.message.edit_text(
                text,
                reply_markup=expedition_cards_keyboard(cards, [])
            )
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка exped_new_start: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("exped_select_"), StateFilter(ExpeditionStates.choosing_cards))
async def exped_select_card(callback: CallbackQuery, state: FSMContext):
    """Выбор/отмена выбора карты"""
    try:
        card_id = int(callback.data.split("_")[-1])

        # Получаем текущее состояние
        data = await state.get_data()
        selected = set(data.get("selected_cards", [])) # data.get("selected_cards", [])

        # Добавляем или удаляем
        if card_id in selected:
            selected.remove(card_id)
            action = "❌ Удалена"
        else:
            if len(selected) >= 3:
                await callback.answer("Можно выбрать только 3 карты!", show_alert=True)
                return
            selected.add(card_id)
            action = "✅ Добавлена"

        # Сохраняем
        await state.update_data(selected_cards=list(selected))

        async with AsyncSessionLocal() as session:
            cards = await ExpeditionManager.get_available_cards(session, callback.from_user.id)

        await callback.message.edit_reply_markup(
            reply_markup=expedition_cards_keyboard(cards, list(selected))
        )

        await callback.answer(action)

    except Exception:
        logger.exception("Ошибка выбора карты")
        await callback.answer("Ошибка", show_alert=True)


@router.callback_query(F.data == "exped_confirm_cards", StateFilter(ExpeditionStates.choosing_cards))
async def exped_confirm_cards(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выбора карт"""
    try:
        data = await state.get_data()
        selected = data.get("selected_cards", [])
        duration = data.get("duration")

        if len(selected) < 1:
            await callback.answer("❌ Выберите хотя бы 1 карту!", show_alert=True)
            return

        # Рассчитываем награды для показа
        duration_map = {"short": 30, "medium": 120, "long": 360}
        async with AsyncSessionLocal() as session:
            rewards = await ExpeditionManager.calculate_rewards(session, selected, duration_map[duration])
            await session.commit()
    
            duration_names = {"short": "30 минут", "medium": "2 часа", "long": "6 часов"}
    
            text = f"""
    <b>🏕️ ПОДТВЕРЖДЕНИЕ ЭКСПЕДИЦИИ</b>
    
    📊 <b>Детали:</b>
    • Длительность: {duration_names[duration]}
    • Карт: {len(selected)} шт.
    • Бонус аниме: {'✅ +50%' if rewards['anime_bonus'] else '❌ нет'}
    
    💰 <b>Награды:</b>
    • Монеты: {rewards['coins']}
    • Пыль: {rewards['dust']}
    • Карта: {rewards['card_chance']}% ({rewards['card_rarity']})
    
    ✅ Отправляем в экспедицию?
    """
            await state.set_state(ExpeditionStates.confirm)
    
            await callback.message.edit_text(
                text,
                reply_markup=expedition_confirm_keyboard(duration, len(selected))
            )
            await callback.answer()
    
    except Exception as e:
        logger.exception(f"Ошибка exped_confirm_cards: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("exped_start_"), StateFilter(ExpeditionStates.confirm))
async def exped_start_final(callback: CallbackQuery, state: FSMContext):
    """Финальный старт экспедиции"""
    try:
        duration = callback.data.replace("exped_start_", "")
        data = await state.get_data()
        selected = data.get("selected_cards", [])

        if not selected:
            await callback.answer("❌ Ошибка: карты не выбраны", show_alert=True)
            await state.clear()
            return

        # Запускаем экспедицию
        async with AsyncSessionLocal() as session:
            expedition = await ExpeditionManager.start_expedition(
                session,
                callback.from_user.id,
                selected,
                duration
            )
        
            # Получаем время окончания
            end_time = expedition.ends_at.strftime("%H:%M %d.%m.%Y")
            time_left = expedition.ends_at - datetime.now()
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
        
            text = f"""
        <b>✅ ЭКСПЕДИЦИЯ НАЧАТА!</b>
        
        📊 <b>Информация:</b>
        • Карт: {len(selected)} шт.
        • Окончание: {end_time}
        • Осталось: {hours}ч {minutes}м
        
        💰 <b>Ожидаемые награды:</b>
        • Монеты: {expedition.reward_coins}
        • Пыль: {expedition.reward_dust}
        • Шанс карты: {expedition.reward_card_chance}%
        
        💡 <b>Совет:</b>
        Возвращайтесь через {hours}ч {minutes}м за наградой!
        """
            # Очищаем состояние
            await state.clear()
        
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню экспедиций", callback_data="expedition")]
                ])
            )
            await callback.answer("Экспедиция начата! 🎉")

    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        await state.clear()
    except Exception as e:
        logger.exception(f"Ошибка exped_start_final: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
        await state.clear()


@router.callback_query(F.data == "exped_list", StateFilter("*"))
async def exped_list(callback: CallbackQuery):
    """Список активных экспедиций"""
    try:
        async with AsyncSessionLocal() as session:
            active, uncollected = await ExpeditionManager.get_active_expeditions(session, callback.from_user.id)
        
            if not active and not uncollected:
                await callback.message.edit_text(
                    "📋 <b>У вас нет активных экспедиций</b>\n\n"
                    "Начните новую экспедицию!",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏕️ Новая экспедиция", callback_data="exped_new_short")],
                        [InlineKeyboardButton(text="« Назад", callback_data="expedition")]
                    ])
                )
                await callback.answer()
                return
        
            text = "<b>📋 МОИ ЭКСПЕДИЦИИ</b>\n\n"
        
            if uncollected:
                text += f"<b>✅ ГОТОВО К ЗАБОРУ ({len(uncollected)}):</b>\n"
                for exp in uncollected[:3]:
                    text += f"• {exp.name} - {exp.reward_coins}💰 {exp.reward_dust}✨\n"
                text += "\n"
        
            if active:
                now = datetime.now()
                text += f"<b>⏳ АКТИВНЫЕ ({len(active)}):</b>\n"
                for exp in active:
                    time_left = exp.ends_at - now
                    minutes = int(time_left.total_seconds() / 60)
                    hours = minutes // 60
                    mins = minutes % 60
        
                    if hours > 0:
                        time_str = f"{hours}ч {mins}м"
                    else:
                        time_str = f"{mins}м"
        
                    text += f"• {exp.name} - ⏳ {time_str}\n"
        
            await callback.message.edit_text(
                text,
                reply_markup=expedition_list_keyboard(active + uncollected, len(uncollected))
            )
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка exped_list: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "exped_claim_all", StateFilter("*"))
async def exped_claim_all(callback: CallbackQuery):
    """Забрать награды всех экспедиций"""
    try:
        async with AsyncSessionLocal() as session:
            rewards = await ExpeditionManager.claim_all_expeditions(session, callback.from_user.id)
            await session.commit()
    
            if rewards["count"] == 0:
                await callback.answer("Нет готовых экспедиций!", show_alert=True)
                return
    
            text = f"""
    <b>🎁 ПОЛУЧЕНЫ НАГРАДЫ!</b>
    
    📊 <b>Экспедиций завершено:</b> {rewards["count"]}
    
    💰 <b>Монеты:</b> +{rewards["coins"]}
    ✨ <b>Пыль:</b> +{rewards["dust"]}
    """
            if rewards["cards"]:
                text += "\n<b>📦 Полученные карты:</b>\n"
                for card in rewards["cards"]:
                    emoji = {'E':'⚪','D':'🟢','C':'⚡','B':'💫','A':'🔮','S':'⭐','ASS':'✨','SSS':'🏆'}.get(card.rarity,'🃏')
                    text += f"• {emoji} {card.card_name} [{card.rarity}]\n"
    
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В меню экспедиций", callback_data="expedition")]
                ])
            )
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка exped_claim_all: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "exped_back_to_cards", StateFilter("*"))
async def exped_back_to_cards(callback: CallbackQuery, state: FSMContext):
    """Вернуться к выбору карт"""
    try:
        data = await state.get_data()
        selected = data.get("selected_cards", [])

        await state.set_state(ExpeditionStates.choosing_cards)
        
        async with AsyncSessionLocal() as session:
            cards = await ExpeditionManager.get_available_cards(session, callback.from_user.id)
    
            text = """
    <b>🏕️ ВЫБЕРИТЕ КАРТЫ</b>
    
    Можно выбрать от 1 до 3 карт.
    ✅ - карта выбрана
    
    💡 <b>Бонус +50%</b> если все карты из одного аниме!
    """
            await callback.message.edit_text(
                text,
                reply_markup=expedition_cards_keyboard(cards, selected)
            )
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка exped_back_to_cards: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "exped_cancel", StateFilter("*"))
async def exped_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена создания экспедиции"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Создание экспедиции отменено",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="expedition")]
        ])
    )
    await callback.answer()