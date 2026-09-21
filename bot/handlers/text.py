import logging
from aiogram import Router, F, Bot
from aiogram.enums import ChatAction
from aiogram.types import Message

from bot.services.processor import process_user_intent
from bot.keyboards.inline import get_main_menu_keyboard

logger = logging.getLogger(__name__)

router = Router(name="text_router")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message, bot: Bot):
    """
    Обработчик входящих текстовых сообщений.
    Анализирует текст сообщения с помощью LLM для извлечения действий,
    поиска по гаражу или ведения учета.
    """
    text = message.text.strip()
    if not text:
        return

    # Быстрые команды на русском
    lowered = text.lower()
    if lowered in {"меню", "кнопки", "панель"}:
        await message.answer("🚘 <b>Главное меню:</b>", reply_markup=get_main_menu_keyboard())
        return

    # Индикация размышления ассистента
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    # Передача в процессор намерений
    await process_user_intent(message=message, text=text, is_voice=False)
