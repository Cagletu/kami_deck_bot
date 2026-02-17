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
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
import random
from game.arena_battle_system import ArenaBattle, BattleCard

# Модели для API
class TurnRequest(BaseModel):
    battle_id: str
    selected_card_id: Optional[int] = None  # Опционально: выбор карты для атаки

class BattleResponse(BaseModel):
    success: bool
    player_cards: Optional[List[Dict]] = None
    enemy_cards: Optional[List[Dict]] = None
    turn: Optional[int] = None
    log: Optional[List[str]] = None
    winner: Optional[str] = None
    rewards: Optional[Dict[str, int]] = None
    error: Optional[str] = None


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
    

# Упрощенный эндпоинт для арены (файл теперь в корне)
@app.get("/arena.html", response_class=HTMLResponse)
async def get_arena():
    """Основной эндпоинт для WebApp"""
    try:
        # Проверяем наличие файла в корне
        arena_path = Path("arena.html")
        if arena_path.exists():
            content = arena_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)

        # Если нет в корне, проверяем в static
        static_path = Path("static/arena.html")
        if static_path.exists():
            content = static_path.read_text(encoding="utf-8")
            return HTMLResponse(content=content)

        # Файл не найден
        return HTMLResponse(
            content="<h1>Arena file not found</h1><p>Checked: arena.html, static/arena.html</p>", 
            status_code=404
        )
    except Exception as e:
        logger.exception(f"Ошибка загрузки arena.html: {e}")
        return HTMLResponse(content=f"<h1>Error: {e}</h1>", status_code=500)
        

# Редирект можно убрать или оставить для обратной совместимости
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


# Тестовый эндпоинт можно оставить
@app.get("/test-arena")
async def test_arena():
    return HTMLResponse("""
    <html>
        <body>
            <h1>Тестовая страница</h1>
            <p>Если вы это видите - сервер работает</p>
            <p><a href="/arena.html">Перейти к арене</a></p>
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


# API эндпоинты
@app.get("/api/battle/{battle_id}", response_model=BattleResponse)
async def get_battle(battle_id: str):
    """Получить состояние битвы"""
    try:
        battle_data = await battle_storage.get_battle(battle_id)
        if not battle_data:
            # Если битва не найдена, создаем тестовую
            return await create_test_battle(battle_id)

        # Преобразуем карты в нужный формат
        player_cards = []
        for card in battle_data.get("player_cards", []):
            if isinstance(card, dict):
                player_cards.append(card)

        enemy_cards = []
        for card in battle_data.get("enemy_cards", []):
            if isinstance(card, dict):
                enemy_cards.append(card)

        return {
            "success": True,
            "player_cards": player_cards,
            "enemy_cards": enemy_cards,
            "turn": battle_data.get("turn", 0)
        }
    except Exception as e:
        logger.exception(f"Error in get_battle: {e}")
        return {
            "success": False, 
            "error": str(e),
            "player_cards": [],
            "enemy_cards": []
        }

@app.post("/api/battle/turn", response_model=BattleResponse)
async def battle_turn(request: TurnRequest):
    """Выполнить ход в битве"""
    try:
        battle_data = await battle_storage.get_battle(request.battle_id)
        if not battle_data:
            return {
                "success": False, 
                "error": "Battle not found",
                "player_cards": [],
                "enemy_cards": []
            }

        # Получаем текущее состояние
        player_cards = battle_data.get("player_cards", [])
        enemy_cards = battle_data.get("enemy_cards", [])
        current_turn = battle_data.get("turn", 0)

        # Простая логика боя (пока тестовая)
        log = []

        # Проверяем что битва не закончена
        if battle_data.get("winner"):
            return {
                "success": True,
                "player_cards": player_cards,
                "enemy_cards": enemy_cards,
                "turn": current_turn,
                "log": ["Битва уже завершена"],
                "winner": battle_data["winner"]
            }

        # Фильтруем живые карты
        alive_players = [c for c in player_cards if c.get("health", 0) > 0]
        alive_enemies = [c for c in enemy_cards if c.get("health", 0) > 0]

        if not alive_players or not alive_enemies:
            return {
                "success": True,
                "player_cards": player_cards,
                "enemy_cards": enemy_cards,
                "turn": current_turn,
                "log": ["Битва уже завершена"],
                "winner": "player" if not alive_enemies else "enemy" if not alive_players else None
            }

        # Каждая живая карта атакует
        new_turn = current_turn + 1
        turn_log = [f"⚔️ Ход {new_turn}"]

        # Атаки игрока
        for player in alive_players:
            if enemy_cards and alive_enemies:
                # Выбираем случайного живого врага
                target = random.choice([e for e in enemy_cards if e.get("health", 0) > 0])

                # Расчет урона
                damage = max(1, player.get("attack", 10) - target.get("defense", 5))
                crit = random.random() < 0.1  # 10% шанс крита
                if crit:
                    damage = int(damage * 1.5)

                # Наносим урон
                old_health = target["health"]
                target["health"] = max(0, old_health - damage)

                # Логируем
                crit_text = " КРИТ!" if crit else ""
                turn_log.append(f"  {player['name']} → {target['name']}: {damage} урона{crit_text}")

                if target["health"] <= 0:
                    turn_log.append(f"  💀 {target['name']} повержен!")

        # Обновляем список живых врагов
        alive_enemies = [c for c in enemy_cards if c.get("health", 0) > 0]

        # Атаки врагов
        for enemy in alive_enemies:
            if player_cards and alive_players:
                # Выбираем случайного живого игрока
                target = random.choice([p for p in player_cards if p.get("health", 0) > 0])

                # Расчет урона
                damage = max(1, enemy.get("attack", 10) - target.get("defense", 5))

                # Наносим урон
                old_health = target["health"]
                target["health"] = max(0, old_health - damage)

                # Логируем
                turn_log.append(f"  👹 {enemy['name']} → {target['name']}: {damage} урона")

                if target["health"] <= 0:
                    turn_log.append(f"  💀 {target['name']} повержен!")

        # Проверяем победителя
        alive_players = [p for p in player_cards if p.get("health", 0) > 0]
        alive_enemies = [c for c in enemy_cards if c.get("health", 0) > 0]

        winner = None
        rewards = None

        if not alive_enemies:
            winner = "player"
            rewards = {
                "coins": 150,
                "dust": 25,
                "rating": 20
            }
            turn_log.append("🎉 ПОБЕДА!")
        elif not alive_players:
            winner = "enemy"
            rewards = {
                "coins": 50,
                "dust": 10,
                "rating": -5
            }
            turn_log.append("😔 Поражение...")

        # Сохраняем обновленное состояние
        battle_data["player_cards"] = player_cards
        battle_data["enemy_cards"] = enemy_cards
        battle_data["turn"] = new_turn
        if winner:
            battle_data["winner"] = winner

        await battle_storage.save_battle(request.battle_id, battle_data)

        return {
            "success": True,
            "player_cards": player_cards,
            "enemy_cards": enemy_cards,
            "turn": new_turn,
            "log": turn_log,
            "winner": winner,
            "rewards": rewards
        }

    except Exception as e:
        logger.exception(f"Error in battle_turn: {e}")
        return {
            "success": False, 
            "error": str(e),
            "player_cards": [],
            "enemy_cards": []
        }

async def create_test_battle(battle_id: str):
    """Создает тестовую битву для разработки"""
    player_cards = [
        {
            "id": 1, "name": "Карта 1", "power": 100, 
            "health": 500, "max_health": 500, "attack": 50, 
            "defense": 30, "level": 1, "rarity": "A"
        },
        {
            "id": 2, "name": "Карта 2", "power": 150, 
            "health": 450, "max_health": 450, "attack": 70, 
            "defense": 40, "level": 2, "rarity": "S"
        },
        {
            "id": 3, "name": "Карта 3", "power": 120, 
            "health": 550, "max_health": 550, "attack": 60, 
            "defense": 35, "level": 1, "rarity": "B"
        }
    ]

    enemy_cards = [
        {
            "id": -1, "name": "Враг 1", "power": 80, 
            "health": 400, "max_health": 400, "attack": 40, 
            "defense": 20, "level": 1, "rarity": "B"
        },
        {
            "id": -2, "name": "Враг 2", "power": 90, 
            "health": 380, "max_health": 380, "attack": 45, 
            "defense": 25, "level": 1, "rarity": "B"
        },
        {
            "id": -3, "name": "Враг 3", "power": 70, 
            "health": 420, "max_health": 420, "attack": 35, 
            "defense": 30, "level": 1, "rarity": "C"
        }
    ]

    battle_data = {
        "player_cards": player_cards,
        "enemy_cards": enemy_cards,
        "turn": 0,
        "created_at": datetime.now().isoformat()
    }

    await battle_storage.save_battle(battle_id, battle_data)

    return {
        "success": True,
        "player_cards": player_cards,
        "enemy_cards": enemy_cards,
        "turn": 0
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": "Internal server error"}
    )
