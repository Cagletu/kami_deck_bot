# main.py (обновленная версия)
import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties

from database.base import engine, AsyncSessionLocal
from bot.handlers import router
from bot.keyboards import set_bot_commands
from sqlalchemy import text


load_dotenv()

# ===== НАСТРОЙКА ЛОГГИРОВАНИЯ =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ===== КОНФИГУРАЦИЯ =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# ===== TELEGRAM БОТ =====
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
dp.include_router(router)

# ===== FASTAPI LIFESPAN =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Запуск Anime Cards Game Bot...")
    await set_bot_commands(bot)
    yield
    # Shutdown
    await bot.session.close()
    await engine.dispose()
    logger.info("🛑 Бот остановлен")

# ===== FASTAPI ПРИЛОЖЕНИЕ =====
app = FastAPI(
    title="Anime Cards Game Bot",
    description="Игровой карточный бот для Telegram",
    version="2.0.0",
    lifespan=lifespan
)

# ===== ЭНДПОИНТЫ =====
@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Anime Cards Game Bot",
        "version": "2.0.0",
        "docs": "/docs"
    }

@app.post("/webhook")
async def telegram_webhook(request: Request):
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != TELEGRAM_WEBHOOK_SECRET:
        logger.warning(f"Неверный секретный токен: {secret_token}")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        update_data = await request.json()
        update = Update(**update_data)
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
    webhook_info = await bot.get_webhook_info()
    return {
        "url": webhook_info.url,
        "pending_update_count": webhook_info.pending_update_count,
        "last_error_message": webhook_info.last_error_message
    }

@app.get("/health")
async def health_check():
    try:
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
            "error": str(e)
        }