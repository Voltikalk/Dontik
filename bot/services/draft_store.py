"""Хранилище неподтверждённых карточек (черновиков).

Данные живут в памяти процесса и живут час. Если бот перезапустится, черновик
пропадёт — поэтому callback_data карточки несёт draft_id, а сам текст карточки
остаётся запасным источником данных (см. callback_handler.parse_card_text).
"""

import time
import uuid
from typing import Dict, Any, Optional

_drafts: Dict[str, Dict[str, Any]] = {}
DRAFT_TTL_SECONDS = 7200  # 2 часа: карточка может пролежать до вечера


def _purge_expired(now: Optional[float] = None) -> None:
    current = now if now is not None else time.time()
    expired = [k for k, v in _drafts.items() if current - v.get("timestamp", 0) > DRAFT_TTL_SECONDS]
    for key in expired:
        _drafts.pop(key, None)


def save_draft(user_id: int, intent: str, data: Dict[str, Any]) -> str:
    """Сохраняет черновик распознанного события и возвращает короткий draft_id."""
    current_time = time.time()
    _purge_expired(current_time)

    draft_id = uuid.uuid4().hex[:8]
    _drafts[draft_id] = {
        "user_id": user_id,
        "intent": intent,
        "data": dict(data or {}),
        "timestamp": current_time,
    }
    return draft_id


def get_draft(draft_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает черновик по его ID (без удаления)."""
    draft = _drafts.get(draft_id)
    if not draft:
        return None
    if time.time() - draft.get("timestamp", 0) > DRAFT_TTL_SECONDS:
        _drafts.pop(draft_id, None)
        return None
    return draft


def update_draft(draft_id: str, data: Dict[str, Any]) -> bool:
    """Обновляет данные черновика (используется при ручной правке карточки)."""
    draft = get_draft(draft_id)
    if not draft:
        return False
    draft["data"].update(data or {})
    draft["timestamp"] = time.time()
    return True


def pop_draft(draft_id: str) -> Optional[Dict[str, Any]]:
    """Извлекает и удаляет черновик."""
    return _drafts.pop(draft_id, None)


def draft_count() -> int:
    """Количество живых черновиков (для диагностики)."""
    _purge_expired()
    return len(_drafts)