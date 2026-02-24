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

from bot.keyboards import set_bot_commands
from sqlalchemy import text

from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path

from services.redis_client import battle_storage
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from database.models import User
from game.arena_battle_system import ArenaBattle, BattleCard


# Модели для API
class TurnRequest(BaseModel):
    battle_id: str
    selected_card_id: Optional[
        int] = None  # Опционально: выбор карты для атаки


class BattleResponse(BaseModel):
    success: bool
    player_cards: Optional[List[Dict]] = None
    enemy_cards: Optional[List[Dict]] = None
    turn: Optional[int] = None
    log: Optional[List[str]] = None
    winner: Optional[str] = None
    rewards: Optional[Dict[str, int]] = None
    error: Optional[str] = None


# Модель для запроса завершения битвы
class BattleFinishRequest(BaseModel):
    battle_id: str
    user_id: int
    result: str  # 'win' или 'lose'
    rewards: Dict[str, Any]  # {'coins': 100, 'dust': 50, 'rating': 10}


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
bot = Bot(token=TELEGRAM_BOT_TOKEN,
          default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
dp.include_router(expedition_router)
dp.include_router(main_router)
dp.include_router(arena_router)


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
app = FastAPI(title="Kami Deck Bot",
              description="Игровой карточный бот для Telegram",
              version="2.0.0",
              lifespan=lifespan)

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
            content=
            "<h1>Arena file not found</h1><p>Checked: arena.html, static/arena.html</p>",
            status_code=404)
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
        return JSONResponse(status_code=500,
                            content={
                                "status": "error",
                                "error": str(e)
                            })


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
@app.get("/api/battle/{battle_id}")
async def get_battle(battle_id: str):
    """Получить состояние битвы"""
    try:
        # ✅ ПРАВИЛЬНО: battle_storage сам добавит префикс battle:
        battle_data = await battle_storage.get_battle(battle_id)

        if not battle_data:
            logger.error(f"Battle {battle_id} not found in Redis")

            # Для отладки - проверим все ключи в Redis
            try:
                import redis.asyncio as redis
                r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
                keys = await r.keys("*")
                logger.info(f"Available Redis keys: {keys}")

                # Проверим есть ли ключ с таким ID
                if f"battle:{battle_id}" in keys:
                    logger.info(f"Key battle:{battle_id} exists but get_battle failed")
                    # Попробуем получить напрямую
                    data = await r.get(f"battle:{battle_id}")
                    if data:
                        import json
                        battle_data = json.loads(data)
                        logger.info("Direct Redis access succeeded")
            except Exception as e:
                logger.error(f"Redis debug error: {e}")

            if not battle_data:
                return {"success": False, "error": "Battle not found"}

        logger.info(f"Battle {battle_id} found: {len(battle_data.get('player_cards', []))} player cards")

        return {
            "success": True,
            "player_cards": battle_data.get("player_cards", []),
            "enemy_cards": battle_data.get("enemy_cards", []),
            "turn": battle_data.get("turn", 0)
        }
    except Exception as e:
        logger.exception(f"Error in get_battle: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/battle/turn")
async def battle_turn(request: TurnRequest):
    """Выполнить ход в битве"""
    try:
        battle_data = await battle_storage.get_battle(request.battle_id)
        if not battle_data:
            return {"success": False, "error": "Battle not found"}

        # Восстанавливаем карты из сохраненных данных
        player_cards_dict = {}
        enemy_cards_dict = {}

        # Создаем объекты карт для боя
        for card_data in battle_data.get("player_cards", []):
            card = BattleCard(id=card_data["id"],
                              user_card_id=card_data["user_card_id"],
                              name=card_data["name"],
                              rarity=card_data.get("rarity", "E"),
                              anime=card_data.get("anime", ""),
                              power=card_data["power"],
                              health=card_data["health"],
                              max_health=card_data["max_health"],
                              attack=card_data["attack"],
                              defense=card_data["defense"],
                              level=card_data.get("level", 1),
                              image_url=card_data.get("image_url", ""),
                              position=card_data.get("position", 0))
            player_cards_dict[card.id] = card

        for card_data in battle_data.get("enemy_cards", []):
            card = BattleCard(id=card_data["id"],
                              user_card_id=card_data.get(
                                  "user_card_id", -card_data["id"]),
                              name=card_data["name"],
                              rarity=card_data.get("rarity", "E"),
                              anime=card_data.get("anime", ""),
                              power=card_data["power"],
                              health=card_data["health"],
                              max_health=card_data["max_health"],
                              attack=card_data["attack"],
                              defense=card_data["defense"],
                              level=card_data.get("level", 1),
                              image_url=card_data.get("image_url", ""),
                              position=card_data.get("position", 0))
            enemy_cards_dict[card.id] = card

        # Создаем объект битвы
        battle = ArenaBattle(list(player_cards_dict.values()),
                             list(enemy_cards_dict.values()))

        # Устанавливаем текущий ход
        battle.turn = battle_data.get("turn", 0)

        # Выполняем ход
        actions = battle.next_turn()

        # Логи для отправки
        battle_log = []
        for action in actions:
            if action.damage > 0:
                crit_text = " КРИТ!" if action.is_critical else ""
                battle_log.append(
                    f"⚔️ {action.attacker_name} атакует {action.defender_name} "
                    f"на {action.damage}{crit_text}")
                if action.is_dead:
                    battle_log.append(f"💀 {action.defender_name} повержен!")

        # Обновляем сохраненные данные
        battle_data["player_cards"] = [
            card.to_dict() for card in player_cards_dict.values()
        ]
        battle_data["enemy_cards"] = [
            card.to_dict() for card in enemy_cards_dict.values()
        ]
        battle_data["turn"] = battle.turn
        battle_data["winner"] = battle.winner

        await battle_storage.save_battle(request.battle_id, battle_data)

        # Собираем actions для анимации
        actions_data = []
        for action in actions:
            actions_data.append({
                "attacker_id": action.attacker_id,
                "attacker_name": action.attacker_name,
                "defender_id": action.defender_id,
                "defender_name": action.defender_name,
                "damage": action.damage,
                "is_critical": action.is_critical,
                "is_dead": action.is_dead
            })

        return {
            "success": True,
            "turn": battle.turn,
            "player_cards": battle_data["player_cards"],
            "enemy_cards": battle_data["enemy_cards"],
            "log": battle_log,
            "actions": actions_data,
            "winner": battle.winner,
            "rewards": {
                "coins": 50,
                "dust": 50,
                "rating": 20
            } if battle.winner == "player" else {
                "coins": 25,
                "dust": 25,
                "rating": -15
            } if battle.winner == "enemy" else None
        }

    except Exception as e:
        logger.exception(f"Error in battle_turn: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/battle/finish")
async def finish_battle(data: BattleFinishRequest):
    """
    Сохраняет результат битвы и начисляет награды пользователю
    """
    logger.info(f"Получен запрос на завершение битвы: battle_id={data.battle_id}, user_id={data.user_id}, result={data.result}")

    async with AsyncSessionLocal() as session:
        try:
            # Получаем пользователя из БД
            user = await session.get(User, data.user_id)

            if not user:
                logger.error(f"Пользователь {data.user_id} не найден")
                return {"success": False, "error": "User not found"}

            # Получаем награды (с безопасным извлечением)
            coins = data.rewards.get("coins", 0)
            dust = data.rewards.get("dust", 0)
            rating = data.rewards.get("rating", 0)

            # Обновляем баланс пользователя
            user.coins += coins
            user.dust += dust
            user.rating += rating

            # Добавляем запись в историю битв (если есть такая таблица)
            # battle_history = BattleHistory(
            #     user_id=data.user_id,
            #     battle_id=data.battle_id,
            #     result=data.result,
            #     coins_earned=coins,
            #     dust_earned=dust,
            #     rating_earned=rating,
            #     created_at=datetime.utcnow()
            # )
            # session.add(battle_history)

            # Обновляем статус битвы (если нужно)
            # await session.execute(
            #     update(Battle)
            #     .where(Battle.id == data.battle_id)
            #     .values(status='finished', winner=data.result)
            # )

            # Сохраняем изменения
            await session.commit()

            logger.info(f"✅ Награды успешно начислены пользователю {data.user_id}: +{coins} монет, +{dust} пыли, +{rating} рейтинга")

            return {
                "success": True,
                "message": "Rewards saved successfully",
                "new_balances": {
                    "coins": user.coins,
                    "dust": user.dust,
                    "rating": user.rating
                }
            }

        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Ошибка при сохранении наград: {str(e)}")
            return {"success": False, "error": str(e)}

# # Дополнительный эндпоинт для получения истории битв пользователя (опционально)
# @app.get("/api/user/{user_id}/battle-history")
# async def get_user_battle_history(user_id: int):
#     """
#     Возвращает историю битв пользователя
#     """
#     async with AsyncSessionLocal() as session:
#         try:
#             # Здесь должен быть запрос к таблице истории битв
#             # history = await session.execute(
#             #     select(BattleHistory)
#             #     .where(BattleHistory.user_id == user_id)
#             #     .order_by(BattleHistory.created_at.desc())
#             #     .limit(50)
#             # )
#             # battles = history.scalars().all()

#             # Пока возвращаем заглушку
#             return {
#                 "success": True,
#                 "history": []  # battles
#             }
#         except Exception as e:
#             logger.error(f"Ошибка получения истории: {str(e)}")
#             return {"success": False, "error": str(e)}


async def create_test_battle(battle_id: str):
    """Создает тестовую битву для разработки"""
    player_cards = [{
        "id": 1,
        "name": "Карта 1",
        "power": 100,
        "health": 500,
        "max_health": 500,
        "attack": 50,
        "defense": 30,
        "level": 1,
        "rarity": "A"
    }, {
        "id": 2,
        "name": "Карта 2",
        "power": 150,
        "health": 450,
        "max_health": 450,
        "attack": 70,
        "defense": 40,
        "level": 2,
        "rarity": "S"
    }, {
        "id": 3,
        "name": "Карта 3",
        "power": 120,
        "health": 550,
        "max_health": 550,
        "attack": 60,
        "defense": 35,
        "level": 1,
        "rarity": "B"
    }]

    enemy_cards = [{
        "id": -1,
        "name": "Враг 1",
        "power": 80,
        "health": 400,
        "max_health": 400,
        "attack": 40,
        "defense": 20,
        "level": 1,
        "rarity": "B"
    }, {
        "id": -2,
        "name": "Враг 2",
        "power": 90,
        "health": 380,
        "max_health": 380,
        "attack": 45,
        "defense": 25,
        "level": 1,
        "rarity": "B"
    }, {
        "id": -3,
        "name": "Враг 3",
        "power": 70,
        "health": 420,
        "max_health": 420,
        "attack": 35,
        "defense": 30,
        "level": 1,
        "rarity": "C"
    }]

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


# тестовый эндпоинт для проверки Redis
@app.get("/debug/redis")
async def debug_redis():
    """Проверка Redis"""
    try:
        import redis.asyncio as redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

        # Получаем все ключи
        keys = await r.keys("*")

        # Получаем один ключ для примера
        sample = None
        if keys:
            sample = await r.get(keys[0])

        return {
            "status":
            "ok",
            "keys_count":
            len(keys),
            "keys":
            [k.decode() if isinstance(k, bytes) else k for k in keys[:10]],
            "sample":
            sample.decode()
            if sample and isinstance(sample, bytes) else str(sample)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/debug/battle/{battle_id}")
async def debug_battle(battle_id: str):
    """Проверка конкретной битвы"""
    try:
        battle_data = await battle_storage.get_battle(battle_id)
        if not battle_data:
            return {"status": "not_found", "battle_id": battle_id}

        # Проверяем структуру данных
        return {
            "status": "found",
            "battle_id": battle_id,
            "has_player_cards": len(battle_data.get("player_cards", [])) > 0,
            "player_cards_count": len(battle_data.get("player_cards", [])),
            "has_enemy_cards": len(battle_data.get("enemy_cards", [])) > 0,
            "enemy_cards_count": len(battle_data.get("enemy_cards", [])),
            "turn": battle_data.get("turn", 0),
            "created_at": battle_data.get("created_at")
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# удалить после тестирования
@app.get("/debug/create-test-battle")
async def create_test_battle_endpoint():
    """Создает тестовую битву для проверки"""
    import uuid
    battle_id = str(uuid.uuid4())

    player_cards = [{
        "id": 1,
        "user_card_id": 1,
        "name": "Тестовая карта 1",
        "rarity": "A",
        "power": 100,
        "health": 500,
        "max_health": 500,
        "attack": 50,
        "defense": 30,
        "level": 1,
        "image_url": "",
        "position": 0,
        "is_alive": True
    }, {
        "id": 2,
        "user_card_id": 2,
        "name": "Тестовая карта 2",
        "rarity": "S",
        "power": 150,
        "health": 450,
        "max_health": 450,
        "attack": 70,
        "defense": 40,
        "level": 2,
        "image_url": "",
        "position": 1,
        "is_alive": True
    }]

    enemy_cards = [{
        "id": -1,
        "user_card_id": -1,
        "name": "Тестовый враг 1",
        "rarity": "B",
        "power": 80,
        "health": 400,
        "max_health": 400,
        "attack": 40,
        "defense": 20,
        "level": 1,
        "image_url": "",
        "position": 0,
        "is_alive": True
    }]

    battle_data = {
        "user_id": 12345,
        "opponent_id": None,
        "player_cards": player_cards,
        "enemy_cards": enemy_cards,
        "turn": 0,
        "winner": None,
        "created_at": datetime.now().isoformat()
    }

    await battle_storage.save_battle(battle_id, battle_data)

    return {
        "success": True,
        "battle_id": battle_id,
        "url": f"/api/battle/{battle_id}",
        "debug_url": f"/debug/battle/{battle_id}"
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Global exception: {exc}")
    return JSONResponse(status_code=500,
                        content={
                            "status": "error",
                            "detail": "Internal server error"
                        })
