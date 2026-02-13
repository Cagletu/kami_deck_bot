from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DB_URL")

# Добавляем настройки пула соединений
engine = create_async_engine(
    DB_URL, 
    echo=False, 
    future=True,
    pool_size=5,  # Размер пула
    max_overflow=10,  # Максимальное количество дополнительных соединений
    pool_pre_ping=True,  # Проверять соединение перед использованием
    pool_recycle=3600  # Пересоздавать соединение через час
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()