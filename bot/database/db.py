import os
from pathlib import Path
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker
)

from bot.config import settings
from bot.database.models import Base

# Гарантируем существование директории data/ для SQLite
db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
if not db_path.startswith(":memory:"):
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

# Создание асинхронного движка SQLAlchemy
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Фабрика асинхронных сессий
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)


async def init_db() -> None:
    """Инициализация базы данных: создание всех таблиц при старте бота."""
    async with engine.begin() as conn:
        # Включаем поддержку внешних ключей для SQLite
        if "sqlite" in settings.DATABASE_URL:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронный контекстный менеджер для получения сессии БД."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
