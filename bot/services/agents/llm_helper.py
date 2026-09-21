import asyncio
import logging
from typing import List, Dict, Optional
from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)


async def call_subagent_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 750,
    preferred_model: Optional[str] = None
) -> str:
    """
    Надежный вызов LLM для субагентов с защитой от лимитов токенов (1000 OTPM у qwen)
    и автоматическим переключением на резервные модели.
    """
    client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.GROQ_API_KEY)

    # Гарантируем, что max_tokens не превышает лимит вывода на тарифе On-Demand (1000 OTPM)
    safe_max_tokens = min(max_tokens, 750)

    # Список моделей по приоритету
    models = []
    if preferred_model:
        models.append(preferred_model)
    for m in [settings.GROQ_MODEL, "openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
        if m not in models:
            models.append(m)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    for model_name in models:
        try:
            # Для gpt-oss моделей лимит выше, можно передать больше токенов при необходимости
            req_tokens = safe_max_tokens if "qwen" in model_name else min(max_tokens, 1200)

            resp = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=req_tokens
            )
            content = resp.choices[0].message.content or ""
            if content.strip():
                return content.strip()
        except Exception as e:
            err_msg = str(e)
            logger.warning(f"[AgentLLM] Модель {model_name} вернула ошибку: {err_msg[:120]}. Пробуем резервную...")
            # Если словили 429, делаем короткую паузу перед следующей моделью
            if "429" in err_msg:
                await asyncio.sleep(0.5)
            continue

    return "Не удалось сформировать отчет субагента из-за временной перегрузки серверов нейросети."
