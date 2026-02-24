from sqlalchemy import Column, Integer, String, BigInteger, DateTime, JSON
from sqlalchemy.sql import func
from database.base import Base


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
    coins = Column(Integer, default=500)
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

    def __repr__(self):
        return f"<User {self.telegram_id} ({self.username})>"
