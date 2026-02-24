import redis.asyncio as redis
import json
import os
import logging
from typing import Optional, Dict


logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

class BattleStorage:
    def __init__(self):
        self.redis = None

    async def connect(self):
        """Подключение к Redis"""
        try:
            self.redis = redis.from_url(REDIS_URL, decode_responses=True)
            await self.redis.ping()
            logger.info("✅ Redis connected successfully")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise

    async def save_battle(self, battle_id: str, battle_data: Dict, ttl: int = 300):
        """Сохраняет состояние боя на 5 минут"""
        if not self.redis:
            await self.connect()
        key = f"battle:{battle_id}"
        await self.redis.setex(
            key,
            ttl,
            json.dumps(battle_data, default=str)
        )
        logger.info(f"✅ Battle {battle_id} saved to Redis")

    async def get_battle(self, battle_id: str) -> Optional[Dict]:
        """Получает состояние боя"""
        if not self.redis:
            await self.connect()
        key = f"battle:{battle_id}"
        data = await self.redis.get(key)
        if data:
            logger.info(f"✅ Battle {battle_id} found in Redis")
            return json.loads(data)
        logger.warning(f"❌ Battle {battle_id} not found in Redis")
        return None

    async def delete_battle(self, battle_id: str):
        """Удаляет состояние боя"""
        if not self.redis:
            await self.connect()
        key = f"battle:{battle_id}"
        await self.redis.delete(key)
        logger.info(f"✅ Battle {battle_id} deleted from Redis")


battle_storage = BattleStorage()
