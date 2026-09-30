"""Тесты отказоустойчивости LLM-слоя: ретраи, цепочка моделей, деградация.

Сеть в тестах не используется — Groq подменяется заглушкой.
"""

import os
import sys
from typing import List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.services import llm  # noqa: E402


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Response:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Delta:
    def __init__(self, content):
        self.content = content


class _Chunk:
    """Стрим-чанк: у choice есть delta, а не message."""

    def __init__(self, content):
        choice = type("C", (), {})()
        choice.delta = _Delta(content)
        self.choices = [choice]


class FakeCompletions:
    """Подмена client.chat.completions.create."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls: List[str] = []

    async def create(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        result = self.behaviour(model, kwargs)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    def __init__(self, behaviour):
        self.chat = type("Chat", (), {})()
        self.completions = FakeCompletions(behaviour)
        self.chat.completions = self.completions


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Убираем реальные паузы между ретраями."""
    slept: List[float] = []

    async def fake_sleep(delay):
        slept.append(delay)

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    return slept


@pytest.fixture()
def patch_client(monkeypatch):
    """Подменяет синглтон клиента и возвращает список вызванных моделей."""
    holder = {}

    def install(behaviour):
        fake = FakeClient(behaviour)
        holder["fake"] = fake
        monkeypatch.setattr(llm, "get_groq_client", lambda: fake)
        return fake.completions.calls

    return install


def rate_limit():
    from openai import RateLimitError

    return RateLimitError(
        message="rate limited",
        response=type("R", (), {"status_code": 429, "headers": {}, "request": None})(),
        body=None,
    )


def server_error():
    from openai import APIStatusError

    return APIStatusError(
        message="server error",
        response=type("R", (), {"status_code": 503, "headers": {}, "request": None})(),
        body=None,
    )


def forbidden():
    from openai import APIStatusError

    return APIStatusError(
        message="access denied",
        response=type("R", (), {"status_code": 403, "headers": {}, "request": None})(),
        body=None,
    )


# --- Ретраи ---

@pytest.mark.asyncio
async def test_retries_on_rate_limit_then_succeeds(patch_client, no_real_sleep):
    state = {"n": 0}

    def behaviour(model, kwargs):
        state["n"] += 1
        if state["n"] < 3:
            return rate_limit()
        return _Response("готово")

    patch_client(behaviour)
    result = await llm.chat_completion([{"role": "user", "content": "hi"}])

    assert result == "готово"
    assert state["n"] == 3
    # Паузы между попытками должны быть, и с ростом (экспонента)
    assert len(no_real_sleep) == 2
    assert no_real_sleep[1] > no_real_sleep[0]


@pytest.mark.asyncio
async def test_retries_on_server_error(patch_client):
    state = {"n": 0}

    def behaviour(model, kwargs):
        state["n"] += 1
        if state["n"] < 2:
            return server_error()
        return _Response("ок")

    patch_client(behaviour)
    assert await llm.chat_completion([{"role": "user", "content": "hi"}]) == "ок"


@pytest.mark.asyncio
async def test_does_not_retry_on_forbidden(patch_client, no_real_sleep):
    """403 — это проблема доступа, а не временная ошибка. Ретраи бессмысленны."""
    calls = patch_client(lambda model, kwargs: forbidden())
    with pytest.raises(Exception):
        await llm.chat_completion([{"role": "user", "content": "hi"}])

    # 403 не ретраится внутри модели, но цепочка моделей всё равно перебирается
    assert len(calls) >= 2
    assert len(no_real_sleep) == 0


# --- Цепочка моделей ---

@pytest.mark.asyncio
async def test_falls_through_to_next_model(patch_client):
    def behaviour(model, kwargs):
        if model == "openai/gpt-oss-120b":
            return server_error()
        return _Response(f"ответ от {model}")

    calls = patch_client(behaviour)
    result = await llm.chat_completion([{"role": "user", "content": "hi"}])

    assert "20b" in result
    assert calls[0] == "openai/gpt-oss-120b"


@pytest.mark.asyncio
async def test_raises_when_all_models_fail(patch_client):
    patch_client(lambda model, kwargs: server_error())
    with pytest.raises(Exception):
        await llm.chat_completion([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_empty_response_triggers_next_model(patch_client):
    """Пустой ответ — тоже повод попробовать другую модель."""
    state = {"n": 0}

    def behaviour(model, kwargs):
        state["n"] += 1
        if state["n"] == 1:
            return _Response("   ")
        return _Response("нормальный ответ")

    calls = patch_client(behaviour)
    assert await llm.chat_completion([{"role": "user", "content": "hi"}]) == "нормальный ответ"
    assert len(calls) == 2


# --- Стриминг ---

@pytest.mark.asyncio
async def test_stream_yields_chunks(patch_client):
    async def fake_stream(model, kwargs):
        assert kwargs["stream"] is True
        for piece in ("Ре", "ша", "ем"):
            yield _Chunk(piece)

    patch_client(fake_stream)
    chunks = [
        chunk
        async for chunk in llm.chat_completion_stream([{"role": "user", "content": "hi"}])
    ]
    assert "".join(chunks) == "Решаем"


@pytest.mark.asyncio
async def test_stream_falls_back_when_all_models_fail(patch_client):
    """Если стриминг не удался ни на одной модели — поднимаем ошибку,
    чтобы вызывающий код откатился на обычный запрос."""
    patch_client(lambda model, kwargs: server_error())
    with pytest.raises(RuntimeError):
        async for _ in llm.chat_completion_stream([{"role": "user", "content": "hi"}]):
            pass


# --- Транскрибация ---

@pytest.mark.asyncio
async def test_transcribe_returns_text(monkeypatch):
    captured = {}

    class FakeAudio:
        class transcriptions:
            @staticmethod
            async def create(**kwargs):
                captured.update(kwargs)
                return "  распознанный текст  "

    class C:
        audio = FakeAudio()

    monkeypatch.setattr(llm, "get_groq_client", lambda: C())
    result = await llm.transcribe_audio(object(), "voice.ogg")

    assert result == "распознанный текст"
    assert captured["language"] == "ru"
    assert captured["model"] == llm.settings.GROQ_WHISPER_MODEL


@pytest.mark.asyncio
async def test_transcribe_retries_then_fails(monkeypatch, no_real_sleep):
    attempts = {"n": 0}

    class FakeAudio:
        class transcriptions:
            @staticmethod
            async def create(**kwargs):
                attempts["n"] += 1
                if attempts["n"] < 3:
                    raise rate_limit()
                return "текст"

    class C:
        audio = FakeAudio()

    monkeypatch.setattr(llm, "get_groq_client", lambda: C())
    assert await llm.transcribe_audio(object(), "v.ogg") == "текст"
    assert attempts["n"] == 3


# --- Ассистент не падает без сети ---

@pytest.mark.asyncio
async def test_answer_query_returns_graceful_text_on_failure(patch_client):
    """Пользователь должен получить вежливое сообщение, а не исключение."""
    from bot.services.assistant import answer_query

    patch_client(lambda model, kwargs: forbidden())
    answer = await answer_query("что делать?")

    assert isinstance(answer, str)
    assert answer.strip()
    assert "Не удалось" in answer


@pytest.mark.asyncio
async def test_stream_assistant_falls_back_to_full_answer(patch_client):
    """Если стрим не пошёл, ассистент доотдаёт ответ обычным запросом."""
    from bot.services.assistant import answer_query

    def behaviour(model, kwargs):
        return _Response("полный ответ")

    patch_client(behaviour)
    answer = await answer_query("вопрос")

    assert answer == "полный ответ"


@pytest.mark.asyncio
async def test_intent_parser_returns_unknown_on_failure(patch_client):
    """Падение LLM не должно ломать хэндлеры — возвращаем безопасный интент."""
    from bot.services.intent_parser import parse_user_intent

    patch_client(lambda model, kwargs: forbidden())
    parsed = await parse_user_intent("заправился")

    assert parsed["intent"] == "unknown"
    assert parsed["data"] == {}