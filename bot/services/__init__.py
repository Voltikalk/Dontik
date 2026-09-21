"""Сервисы внешних API (Groq Whisper, Groq LLM) и вспомогательные модули"""
from .speech_to_text import transcribe_voice
from .intent_parser import parse_user_intent
from .draft_store import save_draft, get_draft, pop_draft

__all__ = [
    "transcribe_voice",
    "parse_user_intent",
    "save_draft",
    "get_draft",
    "pop_draft",
]
