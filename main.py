"""Точка входа Telegram-бота «Пётр — авто-гаражный и повседневный ассистент»."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

from bot.config import settings
from bot.database.db import init_db
from bot.handlers import main_router
from bot.middlewares.auth import AccessMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("auto_garage_bot")

# Порядок важен: первый совпавший роутер забирает апдейт.
BOT_COMMANDS = [
    BotCommand(command="start", description="🚀 Главное меню"),
    BotCommand(command="tasks", description="📋 Задачи и покупки"),
    BotCommand(command="stats", description="📊 Сводка по машине"),
    BotCommand(command="items", description="📦 Вещи в гараже"),
    BotCommand(command="agent", description="🤖 Команда субагентов"),
    BotCommand(command="mail", description="✉️ Входящие письма"),
    BotCommand(command="clear", description="🔄 Сбросить память диалога"),
    BotCommand(command="help", description="💡 Справка и примеры"),
]

PLACEHOLDERS = ("your_bot_token", "your_groq_api_key", "gsk_your", "changeme")


def validate_settings() -> bool:
    """Проверяет критичные переменные окружения до старта."""
    ok = True

    if not settings.BOT_TOKEN or any(p in settings.BOT_TOKEN for p in PLACEHOLDERS):
        logger.error("BOT_TOKEN не задан или содержит значение-заглушку. Заполни BOT_TOKEN в .env")
        ok = False

    if not settings.GROQ_API_KEY or any(p in settings.GROQ_API_KEY for p in PLACEHOLDERS):
        logger.error("GROQ_API_KEY не задан или содержит значение-заглушку. Заполни GROQ_API_KEY в .env")
        ok = False

    if not settings.ALLOWED_TELEGRAM_IDS:
        logger.warning(
            "ALLOWED_TELEGRAM_IDS пуст — бот доступен ЛЮБОМУ пользователю. "
            "Укажи свои ID, если это не так."
        )

    return ok


async def setup_bot_commands(bot: Bot) -> None:
    """Публикует список команд в кнопке меню строки ввода."""
    try:
        await bot.set_my_commands(commands=BOT_COMMANDS, scope=BotCommandScopeDefault())
        logger.info("Команды бота зарегистрированы: %s", ", ".join(c.command for c in BOT_COMMANDS))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось зарегистрировать команды: %s", exc)

    if settings.ALLOWED_TELEGRAM_IDS:
        for user_id in settings.ALLOWED_TELEGRAM_IDS:
            try:
                await bot.set_my_commands(
                    commands=BOT_COMMANDS,
                    scope=BotCommandScopeChat(chat_id=user_id),
                )
            except Exception:  # noqa: BLE001
                pass


async def main() -> None:
    logger.info("Запуск бота…")

    if not validate_settings():
        logger.error("Останов: не заполнены обязательные переменные окружения.")
        sys.exit(1)

    logger.info("Инициализация базы данных…")
    await init_db()
    logger.info("База данных готова (миграции применены).")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # Явный storage: иначе aiogram молча ставит MemoryStorage и состояние
    # теряется при каждом рестарте без предупреждения.
    dp = Dispatcher(storage=MemoryStorage())

    access_middleware = AccessMiddleware()
    dp.message.outer_middleware(access_middleware)
    dp.callback_query.outer_middleware(access_middleware)
    dp.include_router(main_router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        me = await bot.get_me()
        logger.info("Бот авторизован как @%s (ID: %s)", me.username, me.id)

        await setup_bot_commands(bot)
        await _greet_users(bot, me.first_name or "водитель")

        logger.info("Polling запущен.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as exc:  # noqa: BLE001
        logger.error("Критическая ошибка: %s", exc, exc_info=True)
    finally:
        await bot.session.close()
        logger.info("Сессия завершена.")


async def _greet_users(bot: Bot, name: str) -> None:
    """Приветствует разрешённых пользователей при старте, чтобы они знали, что бот жив."""
    for user_id in settings.ALLOWED_TELEGRAM_IDS or []:
        try:
            from bot.emojis import E_HELLO
            from bot.keyboards.inline import get_main_menu_keyboard

            await bot.send_message(
                chat_id=user_id,
                text=f"{E_HELLO} <b>Бот запущен и готов к работе.</b>\n\nПиши или говори — я на связи.",
                reply_markup=get_main_menu_keyboard(),
            )
            logger.info("Отправлено приветствие пользователю %s (%s)", user_id, name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Не удалось поприветствовать %s: %s", user_id, exc)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")