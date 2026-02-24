from sqlalchemy import Column, Integer, ForeignKey, DateTime, Boolean, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.base import Base


class UserCard(Base):
    """Связь пользователь-карточка (инвентарь)"""

    __tablename__ = "user_cards"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    card_id = Column(Integer, ForeignKey("cards.id", ondelete="CASCADE"))

    # Статы копии
    level = Column(Integer, default=1)  # Только уровень, без опыта
    upgrade_points = Column(Integer, default=0)  # Потраченные очки улучшения
    times_upgraded = Column(Integer, default=0)  # Сколько раз улучшали

    # Статусы
    is_in_deck = Column(Boolean, default=False)
    is_favorite = Column(Boolean, default=False)
    is_in_expedition = Column(Boolean, default=False)  # В экспедиции?
    expedition_end_time = Column(DateTime, nullable=True)  # Когда вернется

    # Для боевой системы
    current_power = Column(Integer, default=100)  # Текущая сила (с учетом уровня)
    current_health = Column(Integer, default=100)
    current_attack = Column(Integer, default=10)
    current_defense = Column(Integer, default=10)

    # Статистика использования
    arena_uses = Column(Integer, default=0)
    expedition_uses = Column(Integer, default=0)
    last_used = Column(DateTime, nullable=True)

    # Мета
    obtained_at = Column(DateTime, server_default=func.now())
    source = Column(String, default="pack")  # pack, expedition, arena, achievement

    # Отношения
    user = relationship("User", backref="owned_cards")
    card = relationship("Card")

    def __repr__(self):
        return f"<UserCard #{self.id} {self.card.card_name} Lvl:{self.level}>"
