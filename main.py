# main.py
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
from bot.handlers.expedition import router as expedition_router
from bot.main_handlers import router as main_router
from bot.handlers.arena import router as arena_router
from bot.handlers.arena_callback import router as arena_callback_router


from bot.keyboards import set_bot_commands
from sqlalchemy import text

from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path

from services.redis_client import battle_storage


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
dp.include_router(expedition_router)
dp.include_router(main_router)
dp.include_router(arena_router)
dp.include_router(arena_callback_router)

# ===== FASTAPI LIFESPAN =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Запуск Kami Deck...")
    await set_bot_commands(bot)
    
    if os.getenv("REDIS_URL"):  # только если Redis настроен
        await battle_storage.connect()
    
    yield
    # Shutdown
    await bot.session.close()
    await engine.dispose()
    logger.info("🛑 Бот остановлен")

# ===== FASTAPI ПРИЛОЖЕНИЕ =====
app = FastAPI(
    title="Kami Deck Bot",
    description="Игровой карточный бот для Telegram",
    version="2.0.0",
    lifespan=lifespan
)

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

# ===== ЭНДПОИНТЫ =====

@app.get("/test-arena")
async def test_arena():
    return HTMLResponse("""
    <html>
        <body>
            <h1>Тестовая страница</h1>
            <p>Если вы это видите - сервер работает</p>
            <p><a href="/static/arena.html">Перейти к арене</a></p>
            <p><a href="/arena.html">Перейти к корневой арене</a></p>
        </body>
    </html>
    """)
    

@app.get("/arena.html", response_class=HTMLResponse)
async def get_arena():
    """Основной эндпоинт для WebApp"""
    try:
        # Ищем файл сначала в корне, потом в static
        for path in ["arena.html", "static/arena.html"]:
            if Path(path).exists():
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                return HTMLResponse(content=content)

        # Если файл не найден
        return HTMLResponse(
            content="<h1>Arena file not found</h1><p>Checked: arena.html, static/arena.html</p>", 
            status_code=404
        )
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {e}</h1>", status_code=500)

# Редирект с /static на основной эндпоинт
@app.get("/static/arena.html")
async def static_arena_redirect():
    """Редирект с /static на основной эндпоинт"""
    return HTMLResponse(content="""
    <html>
        <head>
            <meta http-equiv="refresh" content="0;url=/arena.html">
        </head>
        <body>
            <p>Redirecting to /arena.html...</p>
        </body>
    </html>
    """)

# Основной эндпоинт
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": "Internal server error"}
    )
