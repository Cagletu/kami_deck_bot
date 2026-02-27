# services/keep_alive.py
"""
Скрипт для поддержания Replit онлайн через пинги
"""

import asyncio
import aiohttp
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def ping_server():
    """Пинг собственного сервера"""
    url = f"https://{os.getenv('REPLIT_APP_NAME', 'localhost')}.replit.dev/ping"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    logger.info(
                        f"✅ Пинг успешен: {datetime.now().strftime('%H:%M:%S')}"
                    )
                else:
                    logger.warning(f"⚠️ Пинг неудачен: {response.status}")
    except Exception as e:
        logger.error(f"❌ Ошибка пинга: {e}")


async def keep_alive_loop(interval_minutes=5):
    """Цикл пингов"""
    logger.info("🔄 Запуск keep-alive цикла...")

    while True:
        await ping_server()
        await asyncio.sleep(interval_minutes * 60)  # Минуты в секунды


if __name__ == "__main__":
    import os

    # Запускаем только если в Replit
    if os.getenv("REPLIT_APP_NAME"):
        asyncio.run(keep_alive_loop())
