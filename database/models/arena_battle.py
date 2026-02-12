from sqlalchemy import Column, Integer, ForeignKey, DateTime, JSON, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.base import Base

class ArenaBattle(Base):
    """Битва на арене"""
    __tablename__ = "arena_battles"

    id = Column(Integer, primary_key=True)

    # Игроки
    attacker_id = Column(Integer, ForeignKey("users.id"))
    defender_id = Column(Integer, ForeignKey("users.id"))

    # Колоды игроков (ID из user_cards)
    attacker_deck = Column(JSON)  # [1, 2, 3, 4, 5]
    defender_deck = Column(JSON)

    # Результат
    winner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    result = Column(String)  # "attacker_win", "defender_win", "draw"

    # Статистика боя
    rounds = Column(Integer, default=0)
    attacker_damage = Column(Integer, default=0)
    defender_damage = Column(Integer, default=0)

    # Рейтинг
    attacker_rating_change = Column(Integer, default=0)
    defender_rating_change = Column(Integer, default=0)
    attacker_rating_before = Column(Integer)
    defender_rating_before = Column(Integer)

    # Награды (даже проигравший получает)
    attacker_reward_coins = Column(Integer, default=0)
    attacker_reward_dust = Column(Integer, default=0)
    defender_reward_coins = Column(Integer, default=0)
    defender_reward_dust = Column(Integer, default=0)

    # Карта-дроп (шанс)
    dropped_card_id = Column(Integer, ForeignKey("cards.id"), nullable=True)
    dropped_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Время
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)

    # Отношения
    attacker = relationship("User", foreign_keys=[attacker_id])
    defender = relationship("User", foreign_keys=[defender_id])
    winner = relationship("User", foreign_keys=[winner_id])
    dropped_card = relationship("Card")

    def __repr__(self):
        return f"<ArenaBattle #{self.id} {self.attacker_id} vs {self.defender_id}>"