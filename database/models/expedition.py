#database/models/expedition.py
from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    Integer,
    ForeignKey,
    DateTime,
    String,
    JSON,
    Enum,
)  # ← ДОБАВЬТЕ Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.base import Base
import enum


class ExpeditionType(enum.Enum):
    SHORT = "short"  # 30 мин
    MEDIUM = "medium"  # 2 часа
    LONG = "long"  # 6 часов
    SPECIAL = "special"  # Событийная


class ExpeditionStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Expedition(Base):
    """Экспедиция (основной фарм)"""

    __tablename__ = "expeditions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Настройки экспедиции
    name = Column(String)  # "Поход за редкими картами", "Охота на босса"
    expedition_type = Column(Enum(ExpeditionType))
    duration_minutes = Column(Integer)  # 30, 120, 360

    # Карты в экспедиции
    card_ids = Column(ARRAY(Integer))
    # [1, 2, 3] - ID из user_cards

    # Награды (определяются при создании)
    reward_coins = Column(Integer)
    reward_dust = Column(Integer)
    reward_card_rarity = Column(String, nullable=True)  # Если выпадает карта
    reward_card_chance = Column(Integer, default=0)  # Шанс 0-100

    # Бонусы
    anime_bonus = Column(Boolean, default=False)  # Бонус за карты из одного аниме
    rarity_bonus = Column(Integer, default=0)  # Бонус за редкость

    # Время
    started_at = Column(DateTime, server_default=func.now())
    ends_at = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)

    # Статус
    status = Column(Enum(ExpeditionStatus), default=ExpeditionStatus.ACTIVE)
    collected = Column(Boolean, default=False)  # Забрал награду?

    # Отношения
    user = relationship("User", backref="expeditions")

    def __repr__(self):
        return f"<Expedition #{self.id} {self.name} ({self.status.value})>"
