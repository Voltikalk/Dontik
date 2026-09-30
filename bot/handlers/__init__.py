"""Подключение роутеров бота.

Порядок важен: aiogram отдаёт апдейт первому совпавшему роутеру.
1. email / document — специфичные типы контента.
2. input — голос, аудио, видеокружок (универсальный ввод).
3. callback — инлайн-кнопки.
4. general — команды, обычный текст, catch-all. Должен быть последним.
"""

from aiogram import Router

from .callback_handler import router as callback_router
from .document_handler import router as document_router
from .email_handler import router as email_router
from .general_handler import router as general_router
from .input_handler import router as input_router

main_router = Router(name="main_router")
main_router.include_router(email_router)
main_router.include_router(document_router)
main_router.include_router(callback_router)
main_router.include_router(input_router)
main_router.include_router(general_router)

__all__ = [
    "main_router",
    "general_router",
    "callback_router",
    "input_router",
    "document_router",
    "email_router",
]