"""Middleware проверки доступа и синхронизации пользователя."""

import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import settings
from bot.database.crud import get_or_create_user, touch_user
from bot.database.db import get_session
from bot.emojis import E_LOCK

logger = logging.getLogger(__name__)

# Как часто обновлять last_seen_at. Запись на каждое сообщение — лишний расход.
_TOUCH_INTERVAL_SECONDS = 300


class AccessMiddleware(BaseMiddleware):
    """
    Проверяет белый список Telegram ID, авторегистрирует пользователя в БД
    и изредка обновляет время последнего визита.
    """

    def __init__(self) -> None:
        self._last_touch: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        user_id = user.id

        if not settings.is_user_allowed(user_id):
            logger.warning("Отклонён доступ для Telegram ID %s (%s)", user_id, user.full_name)
            if isinstance(event, Message):
                await event.answer(
                    f"{E_LOCK} <b>Доступ ограничен</b>\n\n"
                    f"Ваш Telegram ID: <code>{user_id}</code>\n"
                    f"Для доступа обратитесь к владельцу бота."
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ ограничен.", show_alert=True)
            return

        await self._sync_user(user_id, user.full_name or user.first_name or f"User_{user_id}")
        return await handler(event, data)

    async def _sync_user(self, user_id: int, full_name: str) -> None:
        """Регистрирует пользователя и изредка обновляет last_seen_at."""
        now = time.monotonic()
        if now - self._last_touch.get(user_id, -1e9) < _TOUCH_INTERVAL_SECONDS:
            return
        self._last_touch[user_id] = now

        try:
            async with get_session() as session:
                await get_or_create_user(
                    session=session,
                    telegram_id=user_id,
                    full_name=full_name,
                    is_admin=user_id in (settings.ALLOWED_TELEGRAM_IDS or []),
                )
                await touch_user(session, user_id)
        except Exception as exc:  # noqa: BLE001 - авторегистрация не должна ломать чат
            logger.error("Не удалось синхронизировать пользователя %s: %s", user_id, exc)