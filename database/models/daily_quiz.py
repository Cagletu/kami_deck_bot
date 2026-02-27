# database/models/daily_quiz.py
# ДОБАВИТЬ В БД

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

class DailyQuiz(Base):
    __tablename__ = "daily_quizzes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    question_id = Column(Integer)
    completed_at = Column(DateTime)
    reward_claimed = Column(Boolean, default=False)