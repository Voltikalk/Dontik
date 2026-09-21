import os
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация бота и сервисов через переменные окружения."""

    BOT_TOKEN: str = "your_bot_token_here"
    GROQ_API_KEY: str = "your_groq_api_key_here"
    ALLOWED_TELEGRAM_IDS: Union[List[int], str] = []

    DATABASE_URL: str = "sqlite+aiosqlite:///data/garage.db"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("ALLOWED_TELEGRAM_IDS", mode="before")
    @classmethod
    def parse_allowed_ids(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            return [int(item.strip()) for item in v.split(",") if item.strip()]
        if isinstance(v, (list, tuple)):
            return [int(item) for item in v]
        return []

    def is_user_allowed(self, user_id: int) -> bool:
        """Проверка, разрешен ли доступ пользователю."""
        if not self.ALLOWED_TELEGRAM_IDS:
            return True
        return user_id in self.ALLOWED_TELEGRAM_IDS


settings = Settings()
