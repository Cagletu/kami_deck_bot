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
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
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
app = FastAPI(
    title="Kami Deck Bot",
    description="Игровой карточный бот для Telegram",
    version="2.0.0",
    lifespan=lifespan,
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
            status_code=404,
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
        "docs": "/docs",
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
            status_code=500, content={"status": "error", "error": str(e)}
        )


@app.get("/webhook-info")
async def get_webhook_info():
    webhook_info = await bot.get_webhook_info()
    return {
        "url": webhook_info.url,
        "pending_update_count": webhook_info.pending_update_count,
        "last_error_message": webhook_info.last_error_message,
    }


@app.get("/health")
async def health_check():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


# API эндпоинты
@app.get("/api/battle/{battle_id}")
async def get_battle(battle_id: str):
    """Получить состояние битвы"""
    try:
        logger.info(f"Getting battle {battle_id} from Redis")
        battle_data = await battle_storage.get_battle(battle_id)

        if not battle_data:
            logger.error(f"Battle {battle_id} not found in Redis")
            return {"success": False, "error": "Battle not found"}

        logger.info(
            f"Battle {battle_id} found: {len(battle_data.get('player_cards', []))} player cards"
        )

        # Гарантируем наличие поля is_alive в каждой карте
        for card in battle_data.get("player_cards", []):
            if "is_alive" not in card:
                card["is_alive"] = card.get("health", 0) > 0

        for card in battle_data.get("enemy_cards", []):
            if "is_alive" not in card:
                card["is_alive"] = card.get("health", 0) > 0

        return {
            "success": True,
            "player_cards": battle_data.get("player_cards", []),
            "enemy_cards": battle_data.get("enemy_cards", []),
            "turn": battle_data.get("turn", 0),
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

        # Восстанавливаем карты
        player_cards_dict = {}
        enemy_cards_dict = {}

        for card_data in battle_data.get("player_cards", []):
            card = BattleCard(
                id=card_data["id"],
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
                position=card_data.get("position", 0),
            )
            player_cards_dict[card.id] = card

        for card_data in battle_data.get("enemy_cards", []):
            card = BattleCard(
                id=card_data["id"],
                user_card_id=card_data.get("user_card_id", -card_data["id"]),
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
                position=card_data.get("position", 0),
            )
            enemy_cards_dict[card.id] = card

        # Создаем объект битвы
        battle = ArenaBattle(
            list(player_cards_dict.values()), list(enemy_cards_dict.values())
        )

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
                    f"на {action.damage}{crit_text}"
                )
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
            actions_data.append(
                {
                    "attacker_id": action.attacker_id,
                    "attacker_name": action.attacker_name,
                    "defender_id": action.defender_id,
                    "defender_name": action.defender_name,
                    "damage": action.damage,
                    "is_critical": action.is_critical,
                    "is_dead": action.is_dead,
                }
            )

        # Рассчитываем награды и изменение рейтинга
        rewards = None
        if battle.winner:
            from game.arena_ranks import calculate_rating_change

            player_rating = battle_data.get("player_rating", 1000)
            opponent_rating = battle_data.get("opponent_rating", 1000)

            if battle.winner == "player":
                rating_change = calculate_rating_change(player_rating, opponent_rating, True)
                rewards = {
                    "coins": 50,
                    "dust": 50,
                    "rating": rating_change
                }
            elif battle.winner == "enemy":
                rating_change = calculate_rating_change(player_rating, opponent_rating, False)
                rewards = {
                    "coins": 25,
                    "dust": 25,
                    "rating": rating_change
                }

        return {
            "success": True,
            "turn": battle.turn,
            "player_cards": battle_data["player_cards"],
            "enemy_cards": battle_data["enemy_cards"],
            "log": battle_log,
            "actions": actions_data,
            "winner": battle.winner,
            "rewards": rewards,
        }

    except Exception as e:
        logger.exception(f"Error in battle_turn: {e}")
        return {"success": False, "error": str(e)}


async def create_test_battle(battle_id: str):
    """Создает тестовую битву для разработки"""
    player_cards = [
        {
            "id": 1,
            "name": "Карта 1",
            "power": 100,
            "health": 500,
            "max_health": 500,
            "attack": 50,
            "defense": 30,
            "level": 1,
            "rarity": "A",
        },
        {
            "id": 2,
            "name": "Карта 2",
            "power": 150,
            "health": 450,
            "max_health": 450,
            "attack": 70,
            "defense": 40,
            "level": 2,
            "rarity": "S",
        },
        {
            "id": 3,
            "name": "Карта 3",
            "power": 120,
            "health": 550,
            "max_health": 550,
            "attack": 60,
            "defense": 35,
            "level": 1,
            "rarity": "B",
        },
    ]

    enemy_cards = [
        {
            "id": -1,
            "name": "Враг 1",
            "power": 80,
            "health": 400,
            "max_health": 400,
            "attack": 40,
            "defense": 20,
            "level": 1,
            "rarity": "B",
        },
        {
            "id": -2,
            "name": "Враг 2",
            "power": 90,
            "health": 380,
            "max_health": 380,
            "attack": 45,
            "defense": 25,
            "level": 1,
            "rarity": "B",
        },
        {
            "id": -3,
            "name": "Враг 3",
            "power": 70,
            "health": 420,
            "max_health": 420,
            "attack": 35,
            "defense": 30,
            "level": 1,
            "rarity": "C",
        },
    ]

    battle_data = {
        "player_cards": player_cards,
        "enemy_cards": enemy_cards,
        "turn": 0,
        "created_at": datetime.now().isoformat(),
    }

    await battle_storage.save_battle(battle_id, battle_data)

    return {
        "success": True,
        "player_cards": player_cards,
        "enemy_cards": enemy_cards,
        "turn": 0,
    }


@app.post("/api/battle/result")
async def battle_result(request: Request):
    """Эндпоинт для результатов боя с initData аутентификацией"""
    try:
        # Получаем initData из заголовка
        init_data = request.headers.get("X-Init-Data")
        logger.info(f"🔥 Battle result received with init_data: {init_data}")

        if not init_data:
            return {"success": False, "error": "Missing init_data"}

        # Декодируем init_data
        import base64
        import json

        try:
            # Декодируем из base64
            decoded_json = base64.b64decode(init_data).decode()
            init_data_obj = json.loads(decoded_json)
            logger.info(f"Decoded init_data: {init_data_obj}")

            user_id = init_data_obj.get("user_id")
            battle_id_from_init = init_data_obj.get("battle_id")

            if not user_id:
                return {"success": False, "error": "Invalid init_data: no user_id"}

        except Exception as e:
            logger.error(f"Failed to decode init_data: {e}")
            return {"success": False, "error": f"Invalid init_data: {e}"}

        # Получаем данные из тела запроса
        data = await request.json()
        logger.info(f"Battle result data: {data}")

        action = data.get("action")
        battle_id = data.get("battle_id")
        result = data.get("result")
        rewards = data.get("rewards", {})

        # Проверяем что battle_id совпадает
        if battle_id != battle_id_from_init:
            logger.error(f"Battle ID mismatch: {battle_id} vs {battle_id_from_init}")
            return {"success": False, "error": "Battle ID mismatch"}

        if action != "battle_result":
            return {"success": False, "error": "Invalid action"}

        # Получаем пользователя по telegram_id
        async with AsyncSessionLocal() as session:
            from database.crud import get_user_or_create

            # Важно: user_id из init_data - это telegram_id
            user = await get_user_or_create(session, int(user_id))

            if not user:
                return {"success": False, "error": "User not found"}

            logger.info(f"Updating user {user.id} with battle result: {result}")

            # Начисляем награды
            if result == "win":
                rating_change = rewards.get("rating", 20)
                coins_reward = rewards.get("coins", 50)
                dust_reward = rewards.get("dust", 50)

                user.arena_wins += 1
                user.arena_rating += rating_change
                user.coins += coins_reward
                user.dust += dust_reward

                logger.info(f"🏆 Win: +{coins_reward}💰 +{dust_reward}✨ +{rating_change}⭐")

            elif result == "lose":
                rating_change = rewards.get("rating", -15)
                coins_reward = rewards.get("coins", 25)
                dust_reward = rewards.get("dust", 25)

                user.arena_losses += 1
                user.arena_rating = max(0, user.arena_rating + rating_change)
                user.coins += coins_reward
                user.dust += dust_reward

                logger.info(f"💔 Lose: +{coins_reward}💰 +{dust_reward}✨ {rating_change}⭐")

            # Сохраняем изменения
            await session.commit()

            # Удаляем битву из Redis
            if battle_id:
                await battle_storage.delete_battle(battle_id)

            return {
                "success": True,
                "user": {
                    "id": user.id,
                    "coins": user.coins,
                    "dust": user.dust,
                    "arena_rating": user.arena_rating,
                    "arena_wins": user.arena_wins,
                    "arena_losses": user.arena_losses
                }
            }

    except Exception as e:
        logger.exception(f"Error in battle_result: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/battle/verify")
async def verify_battle_access(request: Request):
    """Проверяет доступ к битве через init_data"""
    try:
        data = await request.json()
        battle_id = data.get("battle_id")
        init_data = data.get("init_data")

        if not battle_id or not init_data:
            return {"success": False, "error": "Missing data"}

        # Декодируем init_data
        import base64
        import json

        try:
            decoded = json.loads(base64.b64decode(init_data).decode())
            user_id = decoded.get("user_id")
            timestamp = decoded.get("timestamp")

            # Проверяем что битва существует и принадлежит этому пользователю
            battle_data = await battle_storage.get_battle(battle_id)
            if not battle_data:
                return {"success": False, "error": "Battle not found"}

            if str(battle_data.get("user_id")) != str(user_id):
                return {"success": False, "error": "Access denied"}

            return {
                "success": True,
                "user_id": user_id,
                "battle_id": battle_id
            }

        except Exception as e:
            return {"success": False, "error": f"Invalid init_data: {e}"}

    except Exception as e:
        logger.exception(f"Error in verify: {e}")
        return {"success": False, "error": str(e)}


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
            "status": "ok",
            "keys_count": len(keys),
            "keys": [k.decode() if isinstance(k, bytes) else k for k in keys[:10]],
            "sample": (
                sample.decode() if sample and isinstance(sample, bytes) else str(sample)
            ),
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
            "created_at": battle_data.get("created_at"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# удалить после тестирования
@app.get("/debug/create-test-battle")
async def create_test_battle_endpoint():
    """Создает тестовую битву для проверки"""
    import uuid

    battle_id = str(uuid.uuid4())

    player_cards = [
        {
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
            "is_alive": True,
        },
        {
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
            "is_alive": True,
        },
    ]

    enemy_cards = [
        {
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
            "is_alive": True,
        }
    ]

    battle_data = {
        "user_id": 12345,
        "opponent_id": None,
        "player_cards": player_cards,
        "enemy_cards": enemy_cards,
        "turn": 0,
        "winner": None,
        "created_at": datetime.now().isoformat(),
    }

    await battle_storage.save_battle(battle_id, battle_data)

    return {
        "success": True,
        "battle_id": battle_id,
        "url": f"/api/battle/{battle_id}",
        "debug_url": f"/debug/battle/{battle_id}",
    }


@app.get("/test-battle-access")
async def test_battle_access():
    """Проверяет доступ к API битвы"""
    import uuid

    battle_id = str(uuid.uuid4())

    # Создаем тестовую битву
    await create_test_battle(battle_id)

    # Пробуем ее получить
    battle_data = await battle_storage.get_battle(battle_id)

    return {
        "created_battle_id": battle_id,
        "battle_exists": battle_data is not None,
        "api_url": f"/api/battle/{battle_id}",
        "test_url": f"/debug/battle/{battle_id}",
    }


@app.get("/test-webapp")
async def test_webapp():
    return HTMLResponse("""
    <html>
    <body>
        <h1>Тест WebApp</h1>
        <script>
            function sendTestData() {
                const tg = window.Telegram?.WebApp;
                if (tg) {
                    tg.sendData(JSON.stringify({
                        action: 'battle_result',
                        result: 'win',
                        rewards: {coins: 50, dust: 50, rating: 20}
                    }));
                    alert('Данные отправлены!');
                } else {
                    alert('WebApp не инициализирован');
                }
            }
        </script>
        <button onclick="sendTestData()">Отправить тестовые данные</button>
    </body>
    </html>
    """)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500, content={"status": "error", "detail": "Internal server error"}
    )
