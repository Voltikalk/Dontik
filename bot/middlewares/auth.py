import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot.config import settings
from bot.database.db import get_session
from bot.database.crud import get_or_create_user

logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    """
    Middleware для проверки белого списка Telegram ID
    и автоматической регистрации пользователя в БД.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        user_id = user.id

        # Проверка белого списка доступа
        if not settings.is_user_allowed(user_id):
            logger.warning(f"Попытка несанкционированного доступа от пользователя {user_id} ({user.full_name})")
            if isinstance(event, Message):
                await event.answer(
                    "⛔ <b>Доступ ограничен</b>\n\n"
                    f"Ваш Telegram ID: <code>{user_id}</code>\n"
                    "Для получения доступа обратитесь к владельцу бота."
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Доступ ограничен.", show_alert=True)
            return

        # Автоматическая синхронизация пользователя с БД
        try:
            async with get_session() as session:
                full_name = user.full_name or user.first_name or f"User_{user_id}"
                is_admin = bool(settings.ALLOWED_TELEGRAM_IDS and user_id in settings.ALLOWED_TELEGRAM_IDS)
                db_user = await get_or_create_user(
                    session=session,
                    telegram_id=user_id,
                    full_name=full_name,
                    is_admin=is_admin
                )
                data["db_user"] = db_user
        except Exception as e:
            logger.error(f"Ошибка сохранения пользователя {user_id} в БД: {e}", exc_info=True)

        return await handler(event, data)
