import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database.db import init_db
from bot.middlewares.auth import AccessMiddleware
from bot.handlers import main_router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("auto_garage_bot")


async def main() -> None:
    """Точка входа в Telegram-бот «Авто-Гараж Ассистент»."""
    logger.info("Запуск бота «Авто-Гараж Ассистент»...")

    # Проверка базовой конфигурации
    if not settings.BOT_TOKEN or "your_bot_token" in settings.BOT_TOKEN:
        logger.warning(
            "⚠️ ВНИМАНИЕ: BOT_TOKEN не указан или задан по умолчанию!\n"
            "Пожалуйста, заполните файл .env действительными токенами бота и Groq API."
        )

    # 1. Инициализация базы данных SQLite и создание таблиц
    logger.info("Инициализация базы данных SQLite...")
    await init_db()
    logger.info("База данных готова к работе.")

    # 2. Инициализация экземпляра бота с HTML парсингом по умолчанию
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # 3. Инициализация диспетчера и регистрация мидлварей
    dp = Dispatcher()

    # Мидлварь авторизации и авторегистрации пользователя в БД
    access_middleware = AccessMiddleware()
    dp.message.outer_middleware(access_middleware)
    dp.callback_query.outer_middleware(access_middleware)

    # 4. Подключение роутеров хэндлеров
    dp.include_router(main_router)

    # 5. Сброс зависших вебхуков и старт polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        bot_user = await bot.get_me()
        logger.info(f"Бот успешно авторизован в Telegram как @{bot_user.username} (ID: {bot_user.id})")
        logger.info("Начинается опрос обновлений (polling)...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
    finally:
        await bot.session.close()
        logger.info("Сессия бота завершена.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
