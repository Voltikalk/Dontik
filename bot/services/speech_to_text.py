import os
import logging
from pathlib import Path
from openai import AsyncOpenAI
from bot.config import settings

logger = logging.getLogger(__name__)


def get_groq_client() -> AsyncOpenAI:
    """Создает или возвращает экземпляр AsyncOpenAI клиента для Groq API."""
    return AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=settings.GROQ_API_KEY
    )


async def transcribe_voice(file_path: str) -> str:
    """
    Асинхронная транскрибация голосового сообщения через Groq Whisper.
    
    - Модель: whisper-large-v3-turbo
    - Язык: ru
    - В блоке finally гарантированно удаляет временный аудиофайл.
    """
    client = get_groq_client()
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Аудиофайл не найден: {file_path}")

        with open(file_path, "rb") as audio_file:
            transcription = await client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
                language="ru",
                response_format="text"
            )
            return transcription.strip() if isinstance(transcription, str) else str(transcription).strip()

    except Exception as e:
        logger.error(f"Ошибка транскрибации Groq Whisper для файла {file_path}: {e}", exc_info=True)
        raise
    finally:
        # Гарантированное удаление временного аудиофайла
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Временный аудиофайл успешно удален: {file_path}")
        except OSError as err:
            logger.warning(f"Не удалось удалить временный аудиофайл {file_path}: {err}")
