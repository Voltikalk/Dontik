"""
Разбор сроков задач из свободной речи.

LLM в intent_parser уже возвращает due_at в ISO, но он может ошибиться или
вернуть пустое значение. Здесь — независимый разбор русских/английских относительных
дат, чтобы задача всё равно получила срок и попала в сортировку.
"""

import re
from datetime import datetime, timedelta
from typing import Optional

_MONTHS_GEN = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "май": 5, "мая": 5,
    "июн": 6, "июль": 7, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10,
    "ноябр": 11, "декабр": 12,
}
_MONTHS_NOM = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11,
    "декабря": 12,
}

_WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среда": 2, "среду": 2, "четверг": 3,
    "пятница": 4, "пятницу": 4, "суббота": 5, "субботу": 5, "воскресенье": 6,
    "воскресенья": 6,
}

_DEFAULT_HOUR = 9  # если срок назван, но время не указано


def _end_of_day(moment: datetime) -> datetime:
    return moment.replace(hour=23, minute=59, second=0, microsecond=0)


def _add_months(moment: datetime, months: int) -> datetime:
    """Прибавляет N месяцев, не падая на 31-м числе коротких месяцев."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return moment.replace(year=year, month=month, day=day)


def parse_due(raw: Optional[str], now: Optional[datetime] = None) -> Optional[datetime]:
    """
    Превращает срок из свободной фразы в datetime.
    Поддерживает: ISO, «сегодня/завтра/послезавтра», дни недели, «через N дней»,
    «N/N», «N месяца», «N+N/N» (14.10), «в 18:00», «утром/днём/вечером».
    """
    if not raw:
        return None

    now = now or datetime.now()
    text = str(raw).strip().lower()
    if not text:
        return None

    # 1. Уже готовый ISO от LLM
    iso_match = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[t ](\d{1,2}):(\d{2}))?", text)
    if iso_match:
        year, month, day = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
        hour = int(iso_match.group(4)) if iso_match.group(4) else _DEFAULT_HOUR
        minute = int(iso_match.group(5)) if iso_match.group(5) else 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            hour, minute = _DEFAULT_HOUR, 0
        try:
            moment = datetime(year, month, day, hour, minute)
        except ValueError:
            return None
        return moment if moment >= now - timedelta(days=1) else None

    # 2. Время суток в тексте.
    # Время распознаём ТОЛЬКО по двоеточию: иначе «14.10» или «25.12» будут
    # съедены как «14:10» и «25:12».
    hour = _DEFAULT_HOUR
    minute = 0
    explicit_time = False

    time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if time_match and int(time_match.group(1)) <= 23:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        explicit_time = True
    elif "утром" in text:
        hour = 9
    elif "днем" in text or "днём" in text:
        hour = 14
    elif "вечером" in text:
        hour = 19
    elif "ночью" in text:
        hour = 23

    # 3. Относительные дни
    if "послезавтра" in text:
        return (now + timedelta(days=2)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "завтра" in text:
        return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "сегодня" in text:
        if explicit_time or "утром" in text or "вечером" in text:
            return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return _end_of_day(now)

    # 4. «через N дней/недель» и «через неделю/месяц»
    rel = re.search(r"через\s+(\d+)\s*(день|дня|дней|недел[юи])", text)
    if rel:
        count = int(rel.group(1))
        delta = timedelta(weeks=count) if "недел" in rel.group(2) else timedelta(days=count)
        return (now + delta).replace(hour=hour, minute=minute, second=0, microsecond=0)

    if "через неделю" in text or "через неделю" in text:
        return (now + timedelta(weeks=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "через месяц" in text:
        return _add_months(now, 1).replace(hour=hour, minute=minute, second=0, microsecond=0)

    # 4b. Указано только время («напомни в 18:30») — считаем сегодня,
    # а если время уже прошло — завтра.
    if explicit_time:
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return today if today >= now else today + timedelta(days=1)

    # 5. День недели («в субботу» = ближайшая суббота)
    for word, target in _WEEKDAYS.items():
        if word in text:
            ahead = (target - now.weekday()) % 7
            if ahead == 0:
                ahead = 7
            return (now + timedelta(days=ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)

    # 6. «14.10» или «14/10» — ближайшая такая дата
    numeric = re.search(r"\b(\d{1,2})[./](\d{1,2})\b", text)
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            for year in (now.year, now.year + 1):
                try:
                    moment = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue
                if moment >= now - timedelta(days=1):
                    return moment

    # 7. «15 сентября» / «15 сентября 2026»
    month_names = "|".join(sorted(_MONTHS_NOM.keys() | set(_MONTHS_GEN.keys()), key=len, reverse=True))
    named = re.search(rf"\b(\d{{1,2}})\s+({month_names})\b(?:\s+(\d{{4}}))?", text)
    if named:
        day = int(named.group(1))
        stem = named.group(2)
        month = _MONTHS_NOM.get(stem) or _MONTHS_GEN.get(stem)
        year = int(named.group(3)) if named.group(3) else now.year
        if month:
            try:
                moment = datetime(year, month, day, hour, minute)
            except ValueError:
                return None
            if moment >= now - timedelta(days=1):
                return moment
            return moment.replace(year=year + 1)

    return None


def resolve_due(due_at_raw: Optional[str], due_date_raw: Optional[str]) -> Optional[datetime]:
    """Сначала доверяем ISO от LLM, при неудаче разбираем текст срока."""
    return parse_due(due_at_raw) or parse_due(due_date_raw)