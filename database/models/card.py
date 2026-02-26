#database/models/card.py
from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.sql import func, text
from database.base import Base
from sqlalchemy.dialects.postgresql import JSONB


class Card(Base):
    """Модель карточки (полностью соответствует существующей таблице)"""

    __tablename__ = "cards"
    __table_args__ = {
        "extend_existing": True
    }  # ВАЖНО: говорим SQLAlchemy расширять существующую таблицу

    id = Column(Integer, primary_key=True)
    original_url = Column(Text, unique=True, nullable=False)
    local_path = Column(Text)
    card_name = Column(Text)
    character_name = Column(Text)
    rarity = Column(Text)  # SSS, ASS, S, A, B, C, D, E
    anime_name = Column(Text)
    anime_link = Column(Text)
    image_data = Column(JSONB)

    # Игровые статы
    base_power = Column(Integer, server_default=text("100"))
    base_health = Column(Integer, server_default=text("100"))
    base_attack = Column(Integer, server_default=text("10"))
    base_defense = Column(Integer, server_default=text("10"))

    # Уровень и прогресс
    level = Column(Integer, server_default=text("1"))
    max_level = Column(Integer, server_default=text("50"))
    experience = Column(Integer, server_default=text("0"))
    file_format = Column(Text, server_default=text("'webp'::text"))

    # Время
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    # ДОБАВЛЯЕМ НОВЫЕ ПОЛЯ которые есть в модели но нет в БД
    # (они добавятся при следующей миграции)
    # updated_at = Column(DateTime, onupdate=func.now())

    def __repr__(self):
        return f"<Card {self.card_name} ({self.rarity})>"
