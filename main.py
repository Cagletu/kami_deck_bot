import os
import random
import logging
import asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, JSON, Boolean, select, ForeignKey
from aiogram import Bot, Dispatcher, types, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from sqlalchemy.sql import func
from sqlalchemy import text
import aiohttp

# ===== НАСТРОЙКА ЛОГГИРОВАНИЯ =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ===== КОНФИГУРАЦИЯ =====
class Settings(BaseSettings):
    DB_URL: str
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_SECRET: str = "supersecret12345"
    TELEGRAM_ADMIN_ID: int
    WEBHOOK_URL: str

    class Config:
        env_file = ".env"


settings = Settings()

# ===== БАЗА ДАННЫХ =====
engine = create_async_engine(settings.DB_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine,
                                       class_=AsyncSession,
                                       expire_on_commit=False)
Base = declarative_base()


# ===== УПРОЩЕННЫЕ МОДЕЛИ =====
class User(Base):
    """Модель игрока"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    language = Column(String, default="ru")

    # Основная валюта
    coins = Column(Integer, default=50000)
    dust = Column(Integer, default=0)  # Пыль за распыление

    # Прогресс
    level = Column(Integer, default=1)
    total_experience = Column(Integer, default=0)
    cards_opened = Column(Integer, default=0)

    # Колода
    selected_deck = Column(JSON, default=list)  # ID карт из user_cards

    # Лимиты и таймеры
    expeditions_slots = Column(Integer, default=2)  # Слоты для экспедиций
    last_trade_time = Column(DateTime, nullable=True)  # Последний обмен
    trade_cooldown_hours = Column(Integer, default=12)  # КД на обмен

    # Статистика
    arena_wins = Column(Integer, default=0)
    arena_losses = Column(Integer, default=0)
    arena_rating = Column(Integer, default=1000)  # Рейтинг Эло
    total_expeditions = Column(Integer, default=0)
    total_duplicates_dusted = Column(Integer, default=0)
    total_cards_upgraded = Column(Integer, default=0)

    # Достижения (битовая маска или JSON)
    achievements = Column(JSON, default=dict)

    # Время
    created_at = Column(DateTime, server_default=func.now())
    last_active = Column(DateTime, server_default=func.now())
    last_daily_tasks = Column(DateTime, nullable=True)  # Когда брал дневные задания


class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True)
    card_name = Column(String, nullable=False)
    rarity = Column(String, nullable=False)  # E, D, C, B, A, S, SS, SSS
    original_url = Column(String, nullable=False)  # ссылка на webp


class UserCard(Base):
    __tablename__ = "user_cards"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"))
    card_id = Column(Integer, ForeignKey("cards.id"))

    user = relationship("User")
    card = relationship("Card")


# =========================
# RARITY SYSTEM
# =========================

RARITY_WEIGHTS = {
    "E": 40,
    "D": 25,
    "C": 15,
    "B": 8,
    "A": 6,
    "S": 3,
    "SS": 2,
    "SSS": 1
}



def roll_rarity():
    rarities = list(RARITY_WEIGHTS.keys())
    weights = list(RARITY_WEIGHTS.values())
    return random.choices(rarities, weights=weights, k=1)[0]

# ===== TELEGRAM БОТ =====
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN,
          default=DefaultBotProperties(parse_mode="HTML"))

storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
async def get_db_session():
    """Получить сессию БД"""
    async with AsyncSessionLocal() as session:
        yield session


async def get_user_or_create(telegram_id: int,
                             username: str = None,
                             first_name: str = None,
                             last_name: str = None) -> User:
    """Получить или создать пользователя"""
    async with AsyncSessionLocal() as session:
        # Ищем пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if user:
            # Обновляем последнюю активность
            user.last_active = datetime.now()
            await session.commit()
            return user

        # Создаем нового пользователя
        new_user = User(telegram_id=telegram_id,
                        username=username,
                        first_name=first_name or "Игрок",
                        last_name=last_name,
                        last_active=datetime.now())

        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        logger.info(f"✅ Создан новый пользователь: {telegram_id}")
        return new_user


# ===== TELEGRAM ХЕНДЛЕРЫ =====
main_router = Router()

@main_router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Обработчик /start"""
    user = await get_user_or_create(telegram_id=message.from_user.id,
                                    username=message.from_user.username,
                                    first_name=message.from_user.first_name,
                                    last_name=message.from_user.last_name)

    welcome_text = f"""
🎮 <b>Добро пожаловать в Kami Deck</b>, {message.from_user.first_name}!

<b>📊 Ваш профиль:</b>
👤 Уровень: <code>{user.level}</code>
💰 Монеты: <code>{user.coins}</code>
✨ Пыль: <code>{user.dust}</code>
🃏 Карточек: <code>{user.cards_opened}</code>

<b>🏆 Статистика:</b>
⚔️ Рейтинг: <code>{user.arena_rating}</code>
📈 Побед/Поражений: <code>{user.arena_wins}/{user.arena_losses}</code>
🏕️ Слотов экспедиций: <code>{user.expeditions_slots}</code>

<b>✨ Основные механики:</b>
• 🏕️ <b>Экспедиции</b> - отправляй карты в походы
• 📦 <b>Пачки карт</b> - открывай и собирай коллекцию
• ⚔️ <b>Арена</b> - сражайся с другими игроками
• 🔄 <b>Обмен</b> - меняйся картами с друзьями

<b>🎯 Доступные команды:</b>
/profile - Ваш профиль
/collection - Коллекция карт
/open_pack - Открыть пачку (100 монет)
/daily - Ежедневная награда
/help - Помощь по игре

<b>🚀 В разработке:</b>
Экспедиции, Арена, Обмен, Улучшение карт
"""

    await message.answer(welcome_text)


@main_router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    """Обработчик /profile"""
    user = await get_user_or_create(message.from_user.id)

    total_battles = user.arena_wins + user.arena_losses
    win_rate = (user.arena_wins / total_battles *
                100) if total_battles > 0 else 0
    time_in_game = datetime.now() - user.created_at
    days = time_in_game.days
    hours = time_in_game.seconds // 3600

    profile_text = f"""
<b>📊 ПРОФИЛЬ ИГРОКА</b>

<b>👤 Основное:</b>
ID: <code>{user.id}</code>
Имя: {user.first_name} {user.last_name or ''}
Уровень: <code>{user.level}</code>

<b>💰 Ресурсы:</b>
Монеты: <code>{user.coins}</code>
Пыль: <code>{user.dust}</code>
Слотов экспедиций: <code>{user.expeditions_slots}</code>

<b>🏆 Статистика:</b>
Карт в коллекции: <code>{user.cards_opened}</code>
Побед: <code>{user.arena_wins}</code>
Поражений: <code>{user.arena_losses}</code>
Винрейт: <code>{win_rate:.1f}%</code>
Рейтинг: <code>{user.arena_rating}</code>

<b>📈 Прогресс:</b>
Экспедиций: <code>{user.total_expeditions}</code>
Карт улучшено: <code>{user.total_cards_upgraded}</code>
Дубликатов распылено: <code>{user.total_duplicates_dusted}</code>

<b>⏰ Время в игре:</b>
Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}
В игре: {days} дней, {hours} часов
"""

    await message.answer(profile_text)


@main_router.message(Command("collection"))
async def cmd_collection(message: types.Message):
    """Обработчик /collection"""
    user = await get_user_or_create(message.from_user.id)

    # TODO: Реальная статистика по редкостям
    collection_text = f"""
<b>🃏 КОЛЛЕКЦИЯ КАРТ</b>

Всего карт: <code>{user.cards_opened}</code>

<b>📊 По редкостям (пример):</b>
SSS: <code>0</code> карт
S: <code>0</code> карт  
A: <code>0</code> карт
B: <code>0</code> карт
C: <code>0</code> карт
D: <code>0</code> карт
E: <code>{user.cards_opened}</code> карт

<b>🎯 Что дальше:</b>
• Откройте первую пачку: /open_pack
• Посмотрите профиль: /profile
• Получите ежедневную награду: /daily

<i>Функция просмотра коллекции в разработке...</i>
"""

    await message.answer(collection_text)


@main_router.message(Command("open_pack"))
async def open_pack(message: types.Message):
    """Открытие пачки карт (только показ)"""
    async with AsyncSessionLocal() as session:
        # Берем пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Сначала напиши /start")
            return

        pack_price = 100
        if user.coins < pack_price:
            await message.answer("❌ Недостаточно монет")
            return

        user.coins += pack_price

        # Выбираем редкость
        rarity = roll_rarity()

        # Берем все карты этой редкости
        result = await session.execute(
            select(Card).where(Card.rarity == rarity)
        )
        cards = result.scalars().all()
        if not cards:
            await message.answer(f"❌ Нет карт редкости {rarity} в базе")
            return

        # Выбираем одну случайную карту
        won_card: Card = random.choice(cards)

        # Формируем подпись
        caption = (
            f"🎉 Тебе выпала карта!\n\n"
            f"✨ {won_card.card_name}\n"
            f"⭐ Редкость: {won_card.rarity}\n\n"
            f"💰 Осталось монет: {user.coins}"
        )

        # Отправка webp по original_url
        await message.answer_photo(
            photo=won_card.original_url,
            caption=caption
        )

        # Показываем текст о пачке
        pack_text = f"""
<b>📦 ВЫ ОТКРЫЛИ ПАЧКУ КАРТ!</b>

💰 Потрачено: <code>{pack_price}</code> монет
💰 Осталось: <code>{user.coins}</code> монет

<b>🎉 Вы получили новую карту!</b>
(Сохранение в базу временно отключено)

🎯 <b>Следующие шаги:</b>
• Открывайте ещё пачки
• Проверяйте /profile
• Ждите экспедиции и арену
"""
        await message.answer(pack_text)

#     pack_text = f"""
# <b>📦 ВЫ ОТКРЫЛИ ПАЧКУ КАРТ!</b>

# 💰 Потрачено: <code>{pack_price}</code> монет
# 💰 Осталось: <code>{user.coins - pack_price}</code> монет

# <b>🎉 Вы получили 3 новые карты!</b>
# (реальная механика в разработке)

# <b>📈 Ваша коллекция теперь:</b>
# Всего карт: <code>{user.cards_opened + 3}</code>

# 🎯 <b>Следующие шаги:</b>
# • Откройте еще пачек для редких карт
# • Проверьте /profile для статистики
# • Ждите экспедиции и арену!

# 🚀 <i>Следующие обновления:</i>
# • Реальное добавление карт из базы
# • Pity-система (гарантированные редкие карты)
# • Просмотр конкретных карт в коллекции
# """

#     await message.answer(pack_text)


@main_router.message(Command("daily"))
async def cmd_daily(message: types.Message):
    """Ежедневная награда"""
    user = await get_user_or_create(message.from_user.id)

    reward_coins = 100

    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        db_user.coins += reward_coins
        db_user.last_daily_tasks = datetime.now()
        await session.commit()

    daily_text = f"""
<b>🎁 ЕЖЕДНЕВНАЯ НАГРАДА</b>

💰 Получено: <code>{reward_coins}</code> монет
💰 Теперь у вас: <code>{user.coins + reward_coins}</code> монет

<b>💡 Что можно сделать:</b>
• Открыть пачку: /open_pack (100 монет)
• Сохранить для будущих обновлений

<b>🚀 Скоро в игре:</b>
🏕️ <b>Экспедиции</b> - основной фарм
⚔️ <b>Арена PvP</b> - сражения с игроками  
🔄 <b>Обмен картами</b> - торговля с друзьями
⭐ <b>Улучшение карт</b> - делай карты сильнее

<b>📅 Завтра снова!</b>
"""

    await message.answer(daily_text)


@main_router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Обработчик /help"""
    help_text = """
<b>❓ ПОМОЩЬ ПО ANIME CARDS GAME</b>

<b>📋 Основные команды:</b>
/start - Начало игры и профиль
/profile - Подробная статистика  
/collection - Коллекция карт
/open_pack - Открыть пачку (100 монет)
/daily - Ежедневная награда (100 монет)
/help - Эта справка

<b>🎮 Текущий функционал:</b>
✅ Регистрация пользователей
✅ Профиль и статистика
✅ Базовая коллекция
✅ Открытие пачек карт
✅ Ежедневные награды

<b>🚀 В РАЗРАБОТКЕ:</b>
🔄 Экспедиции (основной фарм)
🔄 Арена PvP с рейтингом
🔄 Обмен картами между игроками
🔄 Улучшение и распыление карт
🔄 Pity-система для пачек
🔄 Подробный просмотр коллекции

<b>💡 Советы:</b>
• Заходите ежедневно за наградой
• Копите монеты для будущих обновлений
• Следите за новостями в боте

<b>🆘 Поддержка:</b>
По вопросам и предложениям: @Cagletu
"""

    await message.answer(help_text)

dp.include_router(main_router)


# ===== FASTAPI ПРИЛОЖЕНИЕ =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Anime Cards Game Bot",
              description="Игровой карточный бот для Telegram",
              version="1.0.0",
              lifespan=lifespan
             )


# ===== ЭНДПОИНТЫ =====
@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "status": "online",
        "service": "Anime Cards Game Bot",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "webhook_info": "/webhook-info",
        "ping": "/ping"
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    try:
        # Проверяем подключение к БД
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Прием обновлений от Telegram"""
    # Проверка секретного токена
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        logger.warning(f"Неверный секретный токен: {secret_token}")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        # Получаем обновление
        update_data = await request.json()
        update = Update(**update_data)

        # Обрабатываем обновление
        await dp.feed_update(bot=bot, update=update)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(e)}
        )


@app.get("/webhook-info")
async def get_webhook_info():
    """Информация о текущем вебхуке"""
    try:
        webhook_info = await bot.get_webhook_info()
        return {
            "url": webhook_info.url,
            "has_custom_certificate": webhook_info.has_custom_certificate,
            "pending_update_count": webhook_info.pending_update_count,
            "last_error_date": webhook_info.last_error_date,
            "last_error_message": webhook_info.last_error_message,
            "max_connections": webhook_info.max_connections
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/ping")
async def ping():
    """Пинг для поддержания Replit онлайн"""
    return {
        "status": "pong",
        "timestamp": datetime.now().isoformat(),
        "service": "anime-cards-bot"
    }


@app.get("/stats")
async def get_stats():
    """Статистика сервиса"""
    async with AsyncSessionLocal() as session:
        # Считаем пользователей
        result = await session.execute(text("SELECT COUNT(*) FROM users"))
        user_count = result.scalar()

        # Считаем карты из оригинальной таблицы
        result = await session.execute("SELECT COUNT(*) FROM cards")
        total_cards = result.scalar()

        return {
            "users_total": user_count,
            "cards_in_database": total_cards,
            "service_uptime": "since startup",
            "timestamp": datetime.now().isoformat()
        }


# ===== ЗАПУСК ДЛЯ REPLIT =====
# Replit автоматически импортирует и запускает app
# Никакого дополнительного кода здесь не нужно
