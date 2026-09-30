"""Транскрибация голосовых сообщений через Groq Whisper."""

import logging
import os
from pathlib import Path

from bot.services.llm import transcribe_audio

logger = logging.getLogger(__name__)


async def transcribe_voice(file_path: str) -> str:
    """
    Асинхронная транскрибация голосового сообщения.

    Модель и язык берутся из конфигурации (GROQ_WHISPER_MODEL, язык ru).
    Ретраи и перебор моделей делает bot.services.llm.
    В блоке finally временный аудиофайл гарантированно удаляется.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Аудиофайл не найден: {file_path}")

    try:
        with open(file_path, "rb") as audio_file:
            return await transcribe_audio(audio_file, path.name)
    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка транскрибации Groq Whisper (%s): %s", path.name, exc)
        raise
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug("Временный аудиофайл удалён: %s", file_path)
        except OSError as err:
            logger.warning("Не удалось удалить временный аудиофайл %s: %s", file_path, err)