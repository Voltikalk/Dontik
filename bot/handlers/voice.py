import uuid
import logging
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.enums import ChatAction
from aiogram.types import Message

from bot.services.speech_to_text import transcribe_voice
from bot.services.processor import process_user_intent

logger = logging.getLogger(__name__)

router = Router(name="voice_router")


@router.message(F.voice | F.audio)
async def handle_voice_message(message: Message, bot: Bot):
    """
    Обработчик голосовых сообщений и аудиозаметок.
    1. Индицирует действие в Telegram (typing).
    2. Скачивает аудио во временный файл.
    3. Вызывает transcribe_voice (Groq Whisper-large-v3-turbo).
    4. Передает расшифрованный текст в процессор намерений.
    """
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    media = message.voice or message.audio
    if not media:
        return

    # Временный каталог для скачивания файла
    temp_dir = Path("data/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = str(temp_dir / f"voice_{uuid.uuid4().hex[:8]}.ogg")

    try:
        # Скачиваем файл на диск
        await bot.download(file=media.file_id, destination=temp_file_path)

        # Распознаем речь (transcribe_voice гарантированно удалит temp_file_path в finally)
        transcript = await transcribe_voice(file_path=temp_file_path)

        if not transcript or not transcript.strip():
            await message.answer("🔇 Не удалось расслышать слова. Попробуйте записать аудио еще раз чуть громче.")
            return

        # Обрабатываем распознанный текст через универсальный процессор
        await process_user_intent(message=message, text=transcript, is_voice=True)

    except Exception as e:
        logger.error(f"Ошибка при обработке голосового сообщения: {e}", exc_info=True)
        await message.answer(
            "⚠️ <b>Произошла ошибка при обработке голосового сообщения.</b>\n"
            "Убедитесь, что указан корректный <code>GROQ_API_KEY</code> в <code>.env</code>."
        )
