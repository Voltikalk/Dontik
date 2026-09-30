"""
Единая точка доступа к Groq API.

Зачем:
- один AsyncOpenAI-клиент на процесс (httpx-пул соединений, без утечки сокетов);
- автоматические ретраи с экспоненциальной паузой на 429/5xx/таймаутах;
- единая цепочка моделей-фолбэков, чтобы не дублировать её в каждом сервисе.
"""

import asyncio
import logging
import random
from typing import Any, AsyncIterator, Iterable, List, Optional

from openai import AsyncOpenAI, APIConnectionError, APIStatusError, RateLimitError

from bot.config import settings

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Цепочка фолбэков: от самой сильной к быстрым и дешёвым.
_FALLBACK_MODELS: List[str] = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

# Модели, которые не умеют длинные ответы.
_SHORT_CONTEXT_MARKERS = ("qwen",)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.8
RETRY_MAX_DELAY = 6.0


def _build_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=GROQ_BASE_URL,
        api_key=settings.GROQ_API_KEY,
        max_retries=0,  # ретраи делаем сами, чтобы контролировать паузу и логи
        timeout=60.0,
    )


_client: Optional[AsyncOpenAI] = None


def get_groq_client() -> AsyncOpenAI:
    """Возвращает процесс-синглтон AsyncOpenAI клиента."""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def model_chain(preferred: Optional[str] = None) -> List[str]:
    """Строит список моделей для перебора: настройка -> дефолты, без дублей."""
    chain: List[str] = []
    for name in (preferred, settings.GROQ_MODEL, *_FALLBACK_MODELS):
        if name and name not in chain:
            chain.append(name)
    return chain


def max_tokens_for(model: str, requested: int) -> int:
    """Урезает лимит токенов для моделей с коротким контекстом."""
    if any(marker in model for marker in _SHORT_CONTEXT_MARKERS):
        return min(requested, 800)
    return requested


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500
    return isinstance(exc, (asyncio.TimeoutError, TimeoutError))


async def _with_retries(coro_factory, *, label: str, max_retries: int = MAX_RETRIES):
    """Выполняет await coro_factory() с ретраями на 429/5xx/таймаут."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001 - логируем и решаем сами
            last_exc = exc
            if not _is_retryable(exc) or attempt == max_retries:
                raise
            delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
            delay += random.uniform(0, 0.3)  # джиттер, чтобы не бить залпом
            logger.warning(
                "%s: ошибка %s (попытка %d/%d), повтор через %.1fс",
                label, exc.__class__.__name__, attempt, max_retries, delay,
            )
            await asyncio.sleep(delay)
    if last_exc:
        raise last_exc
    return None


async def chat_completion(
    messages: Iterable[dict],
    *,
    preferred_model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1400,
    json_mode: bool = False,
) -> str:
    """
    Выполняет один запрос к чату с перебором моделей-фолбэков.
    Возвращает текст ответа. Бросает последнюю ошибку, если все модели не ответили.
    """
    payload = list(messages)
    last_exc: Optional[Exception] = None

    for model in model_chain(preferred_model):
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": payload,
                "temperature": temperature,
                "max_tokens": max_tokens_for(model, max_tokens),
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = await _with_retries(
                lambda m=model, k=kwargs: get_groq_client().chat.completions.create(**k),
                label=f"chat[{model}]",
            )
            content = (response.choices[0].message.content or "").strip() if response.choices else ""
            if content:
                return content
            logger.warning("Модель %s вернула пустой ответ, пробуем следующую", model)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("Модель %s недоступна: %s", model, exc)

    if last_exc:
        raise last_exc
    raise RuntimeError("Groq: ни одна модель не вернула ответ")


async def chat_completion_stream(
    messages: Iterable[dict],
    *,
    preferred_model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1400,
) -> AsyncIterator[str]:
    """
    Стримит ответ по токенам, перебирая модели-фолбэки.
    Как только модель начала отдавать токены — доучитывает её до конца.
    """
    payload = list(messages)
    yielded_any = False

    for model in model_chain(preferred_model):
        try:
            stream = await get_groq_client().chat.completions.create(
                model=model,
                messages=payload,
                temperature=temperature,
                max_tokens=max_tokens_for(model, max_tokens),
                stream=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Стрим %s недоступен: %s", model, exc)
            continue

        got_something = False
        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    got_something = True
                    yielded_any = True
                    yield delta.content
            if got_something:
                return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Стрим %s оборвался на середине: %s", model, exc)
            if yielded_any:
                return
            continue

    if not yielded_any:
        raise RuntimeError("Groq: стриминг не удался ни на одной модели")


async def transcribe_audio(file_obj, filename: str) -> str:
    """Транскрибация аудио через Whisper с ретраями."""
    response = await _with_retries(
        lambda: get_groq_client().audio.transcriptions.create(
            model=settings.GROQ_WHISPER_MODEL,
            file=file_obj,
            language="ru",
            response_format="text",
            temperature=0.0,
        ),
        label=f"whisper[{filename}]",
    )
    if isinstance(response, str):
        return response.strip()
    return str(response).strip()


def build_token_budget(messages: List[dict], max_chars: int = 12000) -> List[dict]:
    """
    Обрезает историю диалога до бюджета символов, сохраняя целостность сообщений
    и всегда оставляя последнее сообщение пользователя нетронутым.
    """
    if not messages:
        return messages

    head = messages[:-1]
    tail = messages[-1]

    budget = max_chars - len(str(tail.get("content", "")))
    if budget <= 0:
        return [tail]

    trimmed: List[dict] = []
    for msg in reversed(head):
        size = len(str(msg.get("content", "")))
        if size > budget:
            break
        budget -= size
        trimmed.append(msg)

    trimmed.reverse()
    return trimmed + [tail]