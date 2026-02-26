#database/models/trade.py
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    Boolean,
    JSON,
    Enum,
    String,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.base import Base
import enum


class TradeStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"  # Истек срок


class Trade(Base):
    """Обмен картами с ограничениями"""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)

    # Игроки
    from_user_id = Column(Integer, ForeignKey("users.id"))
    to_user_id = Column(Integer, ForeignKey("users.id"))

    # Карты для обмена (ID из user_cards)
    from_user_card_ids = Column(JSON)
    to_user_card_ids = Column(JSON)  # Какие карты просит

    # Ограничения
    max_rarity = Column(String, default="S")  # Максимальная редкость для обмена
    level_reset = Column(Boolean, default=True)  # Сбрасывать уровень?

    # Статус
    status = Column(Enum(TradeStatus), default=TradeStatus.PENDING)

    # Подтверждения
    from_user_confirmed = Column(Boolean, default=False)
    to_user_confirmed = Column(Boolean, default=False)

    # Сообщение
    message = Column(String, nullable=True)

    # Время
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime)  # 24 часа на подтверждение
    completed_at = Column(DateTime, nullable=True)

    # Отношения
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])

    def __repr__(self):
        return f"<Trade #{self.id} {self.status.value}>"
