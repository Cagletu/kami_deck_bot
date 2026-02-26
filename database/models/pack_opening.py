#database/models/pack_opening.py
from sqlalchemy import Column, Integer, ForeignKey, DateTime, JSON, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.base import Base


class PackOpening(Base):
    """Открытие пачки с pity-системой"""

    __tablename__ = "pack_openings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Тип пачки
    pack_type = Column(String)  # "common", "rare", "epic"
    pack_price = Column(Integer)

    # Полученные карты (ID из cards)
    card_ids = Column(JSON)
    rarities = Column(JSON)  # ["E", "C", "B", "A", "S"] для pity-системы

    # Pity-счетчики
    packs_since_last_a = Column(Integer, default=0)
    packs_since_last_s = Column(Integer, default=0)

    # Гарантии
    guaranteed_rarity = Column(String, nullable=True)  # Если сработал pity

    # Время
    opened_at = Column(DateTime, server_default=func.now())

    # Отношения
    user = relationship("User", backref="pack_openings")

    def __repr__(self):
        return f"<PackOpening #{self.id} {self.pack_type} ({len(self.card_ids)} cards)>"
