from pathlib import Path
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker
)

from bot.config import settings
from bot.database.models import Base
from bot.database.migrations import run_migrations

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

def _unicode_lower(value):
    """Юникод-версия lower()."""
    return value.lower() if isinstance(value, str) else value


@event.listens_for(Engine, "connect")
def _register_sqlite_unicode(dbapi_connection, connection_record) -> None:
    """
    Встроенная lower() в SQLite работает только с ASCII, поэтому «Компрессор»
    и «компрессор» считались разными предметами и обновление места хранения
    не срабатывало. Регистрируем Юникод-версию для всех SQLite-соединений.
    """
    if not hasattr(dbapi_connection, "create_function"):
        return  # не SQLite — не трогаем
    try:
        dbapi_connection.create_function("lower", 1, _unicode_lower)
    except Exception:  # noqa: BLE001 - не критично
        pass

# Фабрика асинхронных сессий
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)


async def init_db() -> None:
    """Инициализация базы данных: создание всех таблиц и применение миграций при старте бота."""
    async with engine.begin() as conn:
        # Включаем поддержку внешних ключей для SQLite
        if "sqlite" in settings.DATABASE_URL:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
            # WAL заметно ускоряет запись и не блокирует чтение при параллельных сессиях
            await conn.exec_driver_sql("PRAGMA journal_mode = WAL;")
        await conn.run_sync(Base.metadata.create_all)

    await run_migrations(engine)


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
