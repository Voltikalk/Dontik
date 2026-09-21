import time
import uuid
from typing import Dict, Any, Optional

# Временное хранилище неподтвержденных карточек действий пользователя
# key: draft_id, value: dict
_drafts: Dict[str, Dict[str, Any]] = {}
DRAFT_TTL_SECONDS = 3600  # 1 час жизни черновика


def save_draft(user_id: int, intent: str, data: Dict[str, Any]) -> str:
    """Сохраняет черновик распознанного события и возвращает короткий draft_id."""
    # Очистка устаревших черновиков
    current_time = time.time()
    expired = [k for k, v in _drafts.items() if current_time - v.get("timestamp", 0) > DRAFT_TTL_SECONDS]
    for k in expired:
        _drafts.pop(k, None)

    draft_id = uuid.uuid4().hex[:8]
    _drafts[draft_id] = {
        "user_id": user_id,
        "intent": intent,
        "data": data,
        "timestamp": current_time,
    }
    return draft_id


def get_draft(draft_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает черновик по его ID."""
    return _drafts.get(draft_id)


def pop_draft(draft_id: str) -> Optional[Dict[str, Any]]:
    """Извлекает и удаляет черновик."""
    return _drafts.pop(draft_id, None)
