from aiogram import Router

from .general_handler import router as general_router
from .callback_handler import router as callback_router
from .voice_handler import router as voice_router

main_router = Router(name="main_router")
main_router.include_router(general_router)
main_router.include_router(callback_router)
main_router.include_router(voice_router)

__all__ = ["main_router", "general_router", "callback_router", "voice_router"]
