"""Надёжный вызов LLM для субагентов (ретраи и перебор моделей — в bot.services.llm)."""

import logging
from typing import Optional

from bot.services.llm import chat_completion

logger = logging.getLogger(__name__)

FALLBACK_TEXT = "Не удалось сформировать вывод субагента из-за временной перегрузки нейросети."


async def call_subagent_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 900,
    preferred_model: Optional[str] = None,
) -> str:
    """Вызывает LLM от имени субагента и возвращает текст либо осмысленный откат."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        content = await chat_completion(
            messages,
            preferred_model=preferred_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AgentLLM] Все модели недоступны: %s", exc)
        return FALLBACK_TEXT

    return content.strip() or FALLBACK_TEXT