"""
Лёгкие миграции схемы для SQLite.

SQLite не умеет ALTER TABLE ADD COLUMN с ограничениями и не хранит схему в коде,
поэтому новые колонки доехать до уже существующей data/garage.db могут только так:
создаём новую таблицу, копируем данные, переименовываем, удаляем старую.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from bot.database.models import Base

logger = logging.getLogger(__name__)


async def _table_columns(engine: AsyncEngine, table: str) -> set[str]:
    def _inspect(conn):
        inspector = inspect(conn)
        if table not in inspector.get_table_names():
            return set()
        return {col["name"] for col in inspector.get_columns(table)}

    async with engine.begin() as conn:
        return await conn.run_sync(_inspect)


async def _add_columns_if_missing(engine: AsyncEngine, table: str, columns: dict[str, str]) -> None:
    """Добавляет отсутствующие колонки через ALTER TABLE ADD COLUMN."""
    existing = await _table_columns(engine, table)
    if not existing:
        return

    for name, ddl_type in columns.items():
        if name in existing:
            continue
        logger.info("Миграция: добавляю колонку %s.%s", table, name)
        async with engine.begin() as conn:
            await conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl_type}'))


async def _create_indexes(engine: AsyncEngine, statements: list[str]) -> None:
    for stmt in statements:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception as exc:  # noqa: BLE001 - индекс уже может существовать
            logger.debug("Индекс не создан (%s): %s", stmt, exc)


async def run_migrations(engine: AsyncEngine) -> None:
    """Приводит существующую схему БД к актуальной модели."""
    # tasks: due_at / remind_at / completed_at
    await _add_columns_if_missing(
        engine,
        "tasks",
        {
            "due_at": "DATETIME",
            "remind_at": "DATETIME",
            "completed_at": "DATETIME",
        },
    )

    # users: дата последнего визита — для будущей аналитики активности
    await _add_columns_if_missing(engine, "users", {"last_seen_at": "DATETIME"})

    await _create_indexes(
        engine,
        [
            'CREATE INDEX IF NOT EXISTS ix_tasks_due_at ON tasks (due_at)',
            'CREATE INDEX IF NOT EXISTS ix_chat_history_user_created ON chat_history (user_id, created_at)',
            'CREATE INDEX IF NOT EXISTS ix_item_locations_user_name ON item_locations (user_id, item_name)',
        ],
    )

    logger.info("Миграции схемы БД завершены")


def tables() -> list[str]:
    """Список таблиц текущей модели (для /export)."""
    return sorted(Base.metadata.tables.keys())