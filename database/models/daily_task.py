#database/models/daily_task.py
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    String,
    JSON,
    Boolean,
    Enum,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.base import Base
import enum


class TaskType(enum.Enum):
    OPEN_PACK = "open_pack"
    SEND_EXPEDITION = "send_expedition"
    TRADE_CARD = "trade_card"
    ARENA_BATTLE = "arena_battle"
    UPGRADE_CARD = "upgrade_card"
    DUST_CARD = "dust_card"


class DailyTask(Base):
    """Ежедневные задания (3 из 10 возможных)"""

    __tablename__ = "daily_tasks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Задание
    task_type = Column(Enum(TaskType))
    description = Column(String)  # "Открыть 1 пачку карт"
    current_progress = Column(Integer, default=0)
    required_progress = Column(Integer)  # 1 для большинства заданий

    # Награда
    reward_coins = Column(Integer)
    reward_dust = Column(Integer)
    guaranteed_card_rarity = Column(String)  # E, D, C

    # Статус
    is_completed = Column(Boolean, default=False)
    is_claimed = Column(Boolean, default=False)  # Забрал награду?

    # Время
    assigned_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime)  # Конец дня

    # Отношения
    user = relationship("User", backref="daily_tasks")

    def __repr__(self):
        return f"<DailyTask #{self.id} {self.task_type.value} ({'✓' if self.is_completed else '✗'})>"
