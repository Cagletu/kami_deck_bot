import redis.asyncio as redis
import json
import os
from typing import Optional, Dict

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

class BattleStorage:
    def __init__(self):
        self.redis = None

    async def connect(self):
        """Подключение к Redis"""
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        await self.redis.ping()

    async def save_battle(self, battle_id: str, battle_data: Dict, ttl: int = 300):
        """Сохраняет состояние боя на 5 минут"""
        await self.redis.setex(
            f"battle:{battle_id}",
            ttl,
            json.dumps(battle_data, default=str)
        )

    async def get_battle(self, battle_id: str) -> Optional[Dict]:
        """Получает состояние боя"""
        data = await self.redis.get(f"battle:{battle_id}")
        return json.loads(data) if data else None

    async def delete_battle(self, battle_id: str):
        """Удаляет состояние боя"""
        await self.redis.delete(f"battle:{battle_id}")

battle_storage = BattleStorage()