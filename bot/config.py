"""Конфигурация бота через переменные окружения / файл .env."""

from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация бота и внешних сервисов."""

    BOT_TOKEN: str = "your_bot_token_here"
    GROQ_API_KEY: str = "your_groq_api_key_here"
    # Пустой список = бот доступен всем. См. is_user_allowed.
    ALLOWED_TELEGRAM_IDS: Union[List[int], str] = []

    DATABASE_URL: str = "sqlite+aiosqlite:///data/garage.db"

    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"

    # Темп ответа ассистента (0 — точнее, 1 — свободнее)
    GROQ_TEMPERATURE: float = 0.3

    # Коннектор почты (IMAP / SMTP)
    EMAIL_USER: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    EMAIL_IMAP_HOST: Optional[str] = None
    EMAIL_IMAP_PORT: int = 993
    EMAIL_SMTP_HOST: Optional[str] = None
    EMAIL_SMTP_PORT: int = 465

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("ALLOWED_TELEGRAM_IDS", mode="before")
    @classmethod
    def parse_allowed_ids(cls, v):
        """Парсит список ID из строки «123,456» или из списка."""
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            ids = []
            for chunk in raw.replace(";", ",").split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                try:
                    ids.append(int(chunk))
                except ValueError:
                    raise ValueError(
                        f"ALLOWED_TELEGRAM_IDS: «{chunk}» не похоже на Telegram ID (нужно целое число)"
                    ) from None
            return ids
        if isinstance(v, (list, tuple)):
            return [int(item) for item in v]
        return []

    def is_user_allowed(self, user_id: int) -> bool:
        """Проверяет, разрешён ли доступ пользователю. Пустой белый список = открытый доступ."""
        if not self.ALLOWED_TELEGRAM_IDS:
            return True
        return user_id in self.ALLOWED_TELEGRAM_IDS

    def is_email_configured(self) -> bool:
        """Проверяет, заданы ли реквизиты почты."""
        return bool(self.EMAIL_USER and self.EMAIL_PASSWORD)


settings = Settings()