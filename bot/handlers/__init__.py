from aiogram import Router

from .general_handler import router as general_router
from .callback_handler import router as callback_router
from .voice_handler import router as voice_router
from .document_handler import router as document_router
from .email_handler import router as email_router

main_router = Router(name="main_router")
main_router.include_router(email_router)
main_router.include_router(document_router)
main_router.include_router(general_router)
main_router.include_router(callback_router)
main_router.include_router(voice_router)

__all__ = ["main_router", "general_router", "callback_router", "voice_router", "document_router", "email_router"]


