import re
import logging
import html as py_html
from datetime import datetime
from typing import Dict, Any, List, Optional
from aiogram import html
from aiogram.enums import ParseMode
from aiogram.types import Message, LinkPreviewOptions

from bot.database.models import FuelLog, ServiceLog, ItemLocation, Task
from bot.emojis import (
    E_DROP,
    E_WRENCH,
    E_BOX,
    E_CHART,
    E_SEARCH,
    E_BULB,
    E_LOCATION,
    E_VOICE_TEXT,
    E_NOTE,
    E_LIST,
    E_ALERT,
    E_CLOCK,
    E_CHECK,
)

logger = logging.getLogger(__name__)


# --- Единое форматирование чисел (без опасного replace(",", " ") по всему тексту) ---

def fmt_int(value: Any) -> str:
    """1234567 -> '1 234 567' (неразрывные пробелы для аккуратного выравнивания)."""
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def fmt_money(value: Any, decimals: int = 0) -> str:
    """1234.5 -> '1 235 ₽'."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    formatted = f"{num:,.{decimals}f}".replace(",", " ")
    return f"{formatted} ₽"


def fmt_liters(value: Any) -> str:
    try:
        return f"{float(value):.1f} л"
    except (TypeError, ValueError):
        return "—"


def fmt_km(value: Any) -> str:
    return f"{fmt_int(value)} км"


def _human_due(raw: Optional[str]) -> Optional[str]:
    """Красиво показывает срок задачи: ISO-дата -> '14.10.2026', строка -> как есть."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19], fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return raw


def format_transcript_block(transcript: str, prefix: str = "Распознано") -> str:
    """Сворачивает распознанный текст голоса в раскрываемую цитату."""
    if not transcript or not transcript.strip():
        return ""
    quoted = html.quote(transcript.strip())
    return f"<blockquote expandable>{E_VOICE_TEXT} <b>{html.quote(prefix)}:</b>\n{quoted}</blockquote>"


def format_fuel_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку подтверждения заправки с раскрываемой транскрипцией."""
    liters = data.get("liters")
    cost = data.get("cost")
    odometer = data.get("odometer")
    station = data.get("station") or data.get("station_name")

    try:
        price_per_l = float(cost) / float(liters) if cost and liters else None
    except (TypeError, ValueError, ZeroDivisionError):
        price_per_l = None

    lines = [f"{E_DROP} <b>Заправка</b>\n"]
    lines.append(f"• <b>Литры:</b> <code>{fmt_liters(liters) if liters is not None else 'не указано'}</code>")
    lines.append(f"• <b>Сумма:</b> <code>{fmt_money(cost) if cost is not None else 'не указана'}</code>")
    if price_per_l:
        lines.append(f"• <b>Цена за литр:</b> <code>{fmt_money(price_per_l, 2)}</code>")
    lines.append(f"• <b>Пробег:</b> <code>{fmt_km(odometer) if odometer is not None else 'не указан'}</code>")
    lines.append(f"• <b>АЗС:</b> <i>{html.quote(str(station)) if station else 'не указана'}</i>")

    transcript_block = format_transcript_block(raw_text, "Услышал")
    if transcript_block:
        lines.append("")
        lines.append(transcript_block)

    return "\n".join(lines)


def format_service_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку подтверждения ТО / ремонта."""
    title = data.get("title") or "Техническое обслуживание"
    cost = data.get("cost")
    odometer = data.get("odometer")
    notes = data.get("notes")

    lines = [f"{E_WRENCH} <b>Обслуживание / ремонт</b>\n"]
    lines.append(f"• <b>Работа:</b> <b>{html.quote(str(title))}</b>")
    if odometer is not None:
        lines.append(f"• <b>Пробег:</b> <code>{fmt_km(odometer)}</code>")
    if cost is not None:
        lines.append(f"• <b>Стоимость:</b> <code>{fmt_money(cost)}</code>")
    if notes:
        lines.append(f"• <b>Заметки:</b> <i>{html.quote(str(notes))}</i>")

    transcript_block = format_transcript_block(raw_text, "Услышал")
    if transcript_block:
        lines.append("")
        lines.append(transcript_block)

    return "\n".join(lines)


def format_item_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку сохранения местоположения вещи."""
    item_name = data.get("item_name") or "Вещь"
    location = data.get("location") or "Гараж"

    lines = [f"{E_BOX} <b>Запомнить место хранения</b>\n"]
    lines.append(f"• <b>Предмет:</b> <b>{html.quote(str(item_name))}</b>")
    lines.append(f"• <b>Где лежит:</b> <code>{html.quote(str(location))}</code>")

    transcript_block = format_transcript_block(raw_text, "Услышал")
    if transcript_block:
        lines.append("")
        lines.append(transcript_block)

    return "\n".join(lines)


def format_task_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку новой задачи / покупки."""
    title = data.get("title") or "Задача"
    due = _human_due(data.get("due_date"))

    lines = [f"{E_NOTE} <b>Новая задача</b>\n"]
    lines.append(f"• <b>Дело:</b> <b>{html.quote(str(title))}</b>")
    if due:
        lines.append(f"• <b>Срок:</b> <code>{html.quote(str(due))}</code>")

    transcript_block = format_transcript_block(raw_text, "Услышал")
    if transcript_block:
        lines.append("")
        lines.append(transcript_block)

    return "\n".join(lines)


def format_search_prompt() -> str:
    """Приглашение ввести поисковый запрос вещи."""
    return (
        f"{E_SEARCH} <b>Что ищем в гараже / на даче?</b>\n\n"
        f"Напиши одним словом или фразой, например:\n"
        f"• <i>домкрат</i>\n"
        f"• <i>съёмник подшипников</i>\n"
        f"• <i>запасное колесо</i>"
    )


def format_confirmed(intent: str, data: Dict[str, Any], consumption: Optional[float] = None) -> str:
    """Короткий финальный текст после подтверждения записи."""
    if intent == "fuel":
        liters = data.get("liters")
        cost = data.get("cost")
        text = f"{E_CHECK} <b>Заправка записана</b>"
        if liters is not None and cost is not None:
            text += f" — {fmt_liters(liters)} на {fmt_money(cost)}"
        if consumption:
            text += f"\n{E_DROP} Расход: <code>{consumption:.1f} л / 100 км</code>"
        return text

    if intent == "service":
        text = f"{E_CHECK} <b>Запись ТО / ремонта сохранена</b>"
        title = data.get("title")
        if title:
            text += f"\n• <b>{html.quote(str(title))}</b>"
        cost = data.get("cost")
        if cost is not None:
            text += f" на <code>{fmt_money(cost)}</code>"
        return text

    if intent == "item_save":
        item = data.get("item_name") or "Вещь"
        loc = data.get("location") or "Гараж"
        return (
            f"{E_CHECK} <b>Место сохранено</b>\n"
            f"• <b>{html.quote(str(item))}</b> → <code>{html.quote(str(loc))}</code>"
        )

    if intent == "task_save":
        title = data.get("title") or "Задача"
        due = _human_due(data.get("due_date"))
        due_str = f" <i>(срок: {html.quote(str(due))})</i>" if due else ""
        return f"{E_CHECK} Задача «<b>{html.quote(str(title))}</b>»{due_str} добавлена"

    return f"{E_CHECK} <b>Записано</b>"


def format_tasks_list(tasks: List[Task]) -> str:
    """Форматирует список задач: просроченные и срочные подсвечиваются, срок разбирается."""
    if not tasks:
        return f"{E_LIST} <b>Активных задач нет.</b>\n\nСкажи или напиши: <i>«Запиши купить омывайку и съездить на дачу»</i>"

    now = datetime.now()
    lines = [f"{E_LIST} <b>Активные задачи</b> ({len(tasks)}):\n"]

    for idx, task in enumerate(tasks, 1):
        due = _human_due(task.due_date)
        marker = ""

        if task.due_at:
            if task.due_at < now:
                marker = f" {E_ALERT} <i>просрочено</i>"
            elif (task.due_at - now).total_seconds() < 24 * 3600:
                marker = f" {E_CLOCK} <i>скоро</i>"

        due_str = f"\n    {E_CLOCK} срок: <code>{html.quote(str(due))}</code>{marker}" if due else ""
        lines.append(f"{idx}. <b>{html.quote(task.title)}</b>{due_str}")

    return "\n".join(lines)


def format_found_items(items: List[ItemLocation], query: str) -> str:
    """Форматирует результаты поиска вещей в гараже."""
    if not items:
        return (
            f"{E_SEARCH} По запросу «<b>{html.quote(query)}</b>» ничего не найдено.\n\n"
            f"{E_BULB} Чтобы бот запомнил вещь, просто скажите или напишите, например:\n"
            "<i>«Положил домкрат в левый угол у ворот»</i>"
        )

    lines = [f"{E_LOCATION} <b>Найдено в гараже / на даче (запрос: {html.quote(query)}):</b>\n"]
    for idx, it in enumerate(items, 1):
        updated = it.updated_at.strftime("%d.%m.%Y")
        lines.append(
            f"{idx}. <b>{html.quote(it.item_name)}</b>\n"
            f"   ↳ {E_LOCATION} <code>{html.quote(it.location)}</code> <i>(обновлено: {updated})</i>"
        )
    return "\n".join(lines)


def format_all_items_list(items: List[ItemLocation]) -> str:
    """Форматирует полный список вещей пользователя."""
    if not items:
        return f"{E_BOX} В гараже пока ничего не записано. Скажите или напишите, что и куда вы положили!"

    lines = [f"{E_BOX} <b>Список вещей на хранении:</b>\n"]
    for idx, it in enumerate(items, 1):
        lines.append(f"{idx}. <b>{html.quote(it.item_name)}</b> — <code>{html.quote(it.location)}</code>")
    lines.append(f"\n{E_BULB} <i>Чтобы найти конкретную вещь, спросите «Где лежит ...?»</i>")
    return "\n".join(lines)


def format_fuel_history(logs: List[FuelLog]) -> str:
    """Форматирует историю заправок."""
    if not logs:
        return f"{E_DROP} История заправок пока пуста."

    lines = [f"{E_DROP} <b>Последние заправки:</b>\n"]
    for it in logs:
        date_str = it.date.strftime("%d.%m.%Y")
        station_str = f" ({html.quote(it.station_name)})" if it.station_name else ""
        price = (it.cost / it.liters) if it.liters else None
        price_str = f" · {fmt_money(price, 2)}/л" if price else ""
        lines.append(
            f"• <b>{date_str}</b>{station_str}: "
            f"<code>{fmt_liters(it.liters)}</code> на <code>{fmt_money(it.cost)}</code>"
            f"{price_str} · <code>{fmt_km(it.odometer)}</code>"
        )
    return "\n".join(lines)


def format_service_history(logs: List[ServiceLog]) -> str:
    """Форматирует историю ТО."""
    if not logs:
        return f"{E_WRENCH} История обслуживания и ремонтов пока пуста."

    lines = [f"{E_WRENCH} <b>Последние записи ТО и сервиса:</b>\n"]
    for it in logs:
        date_str = it.date.strftime("%d.%m.%Y")
        cost_str = f" на <code>{fmt_money(it.cost)}</code>" if it.cost else ""
        lines.append(
            f"• <b>{date_str}</b>: <b>{html.quote(it.title)}</b>{cost_str} · "
            f"<code>{fmt_km(it.odometer)}</code>"
        )
    return "\n".join(lines)


def format_stats_summary(fuel_stats: Dict[str, Any]) -> str:
    """Форматирует общую статистику по расходам."""
    total_liters = fuel_stats.get("total_liters", 0.0)
    total_cost = fuel_stats.get("total_cost", 0.0)
    avg_price = fuel_stats.get("avg_price_per_liter", 0.0)
    avg_consumption = fuel_stats.get("avg_consumption", 0.0)
    count = fuel_stats.get("count", 0)

    lines = [
        f"{E_CHART} <b>Сводка расходов на топливо</b> ({count} заправок):\n",
        f"• <b>Всего заправлено:</b> <code>{fmt_liters(total_liters)}</code>",
        f"• <b>Общие затраты:</b> <code>{fmt_money(total_cost)}</code>",
        f"• <b>Средняя цена за литр:</b> <code>{fmt_money(avg_price, 2)}</code>",
    ]
    if avg_consumption > 0:
        lines.append(f"• <b>Средний расход:</b> <code>{avg_consumption:.1f} л / 100 км</code>")
    lines.append(f"\n{E_BULB} _История заправок доступна кнопкой выше._")
    return "\n".join(lines)

from pylatexenc.latex2text import LatexNodes2Text, get_default_latex_context_db, MacroTextSpec

# Настройка парсера LaTeX в Unicode
_latex_db = get_default_latex_context_db()

def _frac_repl(node, l2tobj):
    num = l2tobj.nodelist_to_text([node.nodeargs[0]]).strip()
    den = l2tobj.nodelist_to_text([node.nodeargs[1]]).strip()
    has_op_num = any(c in num for c in ['+', '-', '='])
    has_op_den = any(c in den for c in ['+', '-', '='])
    n_str = f'({num})' if has_op_num else num
    d_str = f'({den})' if has_op_den else den
    return f'{n_str} / {d_str}'

def _sqrt_repl(node, l2tobj):
    inner = l2tobj.nodelist_to_text([node.nodeargs[0]]).strip()
    if len(inner) <= 4 and not any(op in inner for op in '+-*/±= '):
        return f'√{inner}'
    return f'√({inner})'

_latex_db.add_context_category('math_overrides', macros=[
    MacroTextSpec('frac', simplify_repl=_frac_repl),
    MacroTextSpec('sqrt', simplify_repl=_sqrt_repl),
    MacroTextSpec('displaystyle', simplify_repl=''),
    MacroTextSpec('textstyle', simplify_repl=''),
], prepend=True)

_latex_converter = LatexNodes2Text(latex_context=_latex_db)

# --- Словари символов Unicode для степеней и индексов ---
SUPERSCRIPTS = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
    '/': '⁄',  # fraction slash U+2044 для степеней вроде 3/2 -> ³⁄²
    'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ', 'd': 'ᵈ', 'e': 'ᵉ',
    'f': 'ᶠ', 'g': 'ᵍ', 'h': 'ʰ', 'i': 'ⁱ', 'j': 'ʲ',
    'k': 'ᵏ', 'l': 'ˡ', 'm': 'ᵐ', 'n': 'ⁿ', 'o': 'ᵒ',
    'p': 'ᵖ', 'r': 'ʳ', 's': 'ˢ', 't': 'ᵗ', 'u': 'ᵘ',
    'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ', 'y': 'ʸ', 'z': 'ᶻ',
    'A': 'ᴬ', 'B': 'ᴮ', 'D': 'ᴰ', 'E': 'ᴱ', 'G': 'ᴳ',
    'H': 'ᴴ', 'I': 'ᴵ', 'J': 'ᴶ', 'K': 'ᴷ', 'L': 'ᴸ',
    'M': 'ᴹ', 'N': 'ᴺ', 'O': 'ᴼ', 'P': 'ᴾ', 'R': 'ᴿ',
    'T': 'ᵀ', 'U': 'ᵁ', 'W': 'ᵂ',
    'α': 'ᵅ', 'β': 'ᵝ', 'γ': 'ᵞ', 'δ': 'ᵟ', 'θ': 'ᶿ', 'φ': 'ᵠ', 'χ': 'ᵡ',
}

SUBSCRIPTS = {
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
    '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
    '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
    'a': 'ₐ', 'e': 'ₑ', 'h': 'ₕ', 'i': 'ᵢ', 'j': 'ⱼ',
    'k': 'ₖ', 'l': 'ₗ', 'm': 'ₘ', 'n': 'ₙ', 'o': 'ₒ',
    'p': 'ₚ', 'r': 'ᵣ', 's': 'ₛ', 't': 'ₜ', 'u': 'ᵤ',
    'v': 'ᵥ', 'x': 'ₓ'
}

GREEK_MATH_MAP = {
    r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ',
    r'\epsilon': 'ε', r'\zeta': 'ζ', r'\eta': 'η', r'\theta': 'θ',
    r'\iota': 'ι', r'\kappa': 'κ', r'\lambda': 'λ', r'\mu': 'μ',
    r'\nu': 'ν', r'\xi': 'ξ', r'\pi': 'π', r'\rho': 'ρ',
    r'\sigma': 'σ', r'\tau': 'τ', r'\phi': 'φ', r'\chi': 'χ',
    r'\psi': 'ψ', r'\omega': 'ω', r'\Gamma': 'Γ', r'\Delta': 'Δ',
    r'\Theta': 'Θ', r'\Lambda': 'Λ', r'\Xi': 'Ξ', r'\Pi': 'Π',
    r'\Sigma': 'Σ', r'\Phi': 'Φ', r'\Psi': 'Ψ', r'\Omega': 'Ω',
    r'\infty': '∞'
}


def to_sup(text: str) -> str:
    """Конвертирует строку в надстрочные символы Unicode с поддержкой дробей и греческих букв."""
    for k, v in GREEK_MATH_MAP.items():
        text = text.replace(k, v)
    text = text.replace('^', '')
    return "".join(SUPERSCRIPTS.get(c, c) for c in text)


def to_sub(text: str) -> str:
    """Конвертирует строку в подстрочные символы Unicode."""
    for k, v in GREEK_MATH_MAP.items():
        text = text.replace(k, v)
    text = text.replace('_', '')
    return "".join(SUBSCRIPTS.get(c, c) for c in text)


def strip_boxed(text: str) -> str:
    """Безопасно извлекает содержимое \\boxed{...} с учетом произвольной вложенности фигурных скобок."""
    while r'\boxed{' in text:
        idx = text.find(r'\boxed{')
        start = idx + len(r'\boxed{')
        depth = 1
        pos = start
        while pos < len(text) and depth > 0:
            if text[pos] == '{':
                depth += 1
            elif text[pos] == '}':
                depth -= 1
            pos += 1
        if depth == 0:
            inner = text[start:pos - 1]
            text = text[:idx] + inner + text[pos:]
        else:
            break
    return text


def preprocess_latex(s: str) -> str:
    """Предварительная очистка команд разметки LaTeX перед парсингом формулы."""
    s = strip_boxed(s)
    s = re.sub(r'\\(displaystyle|textstyle|limits|nolimits)\b', '', s)
    s = re.sub(r'\\(left|right)\s*([()\[\]{}|.])', r'\2', s)
    s = re.sub(r'\\(left|right)\b', '', s)
    s = re.sub(r'\\quad', '   ', s)
    s = re.sub(r'\\qquad', '     ', s)

    # Десятичная точка/запятая в числах с тонким пробелом: 1\,777 -> 1.777
    s = re.sub(r'(\d)\\,(\d)', r'\1.\2', s)
    s = re.sub(r'\\,\s*', ' ', s)
    s = re.sub(r'\\[;!]', ' ', s)

    # Пробелы после функций и перевод в стандартную русскую нотацию
    s = re.sub(r'([a-zA-Z0-9])\\(sin|cos|tan|cot|ln|log|exp|arcsin|arccos|arctan)\b', r'\1 \\\2', s)
    s = re.sub(r'\\(sin|cos|tan|cot|ln|log|exp|arcsin|arccos|arctan)\b(?!\s)', r'\\\1 ', s)
    s = re.sub(r'\\tan\b', 'tg', s)
    s = re.sub(r'\\cot\b', 'ctg', s)
    s = re.sub(r'\\arctan\b', 'arctg', s)

    # Пределы интегралов и сумм ДО удаления скобок парсером
    s = re.sub(r'\\int_0\^\\?infty\b', '∫₀^∞ ', s)
    s = re.sub(r'\\int_\{0\}\^\{\\?infty\}', '∫₀^∞ ', s)
    s = re.sub(r'\\int\b', '∫ ', s)
    s = re.sub(r'\\sum_\{([^}]+)\}\^\{\\?infty\}', lambda m: f'∑{to_sub(m.group(1))}^∞ ', s)
    s = re.sub(r'\\sum_\{([^}]+)\}\^([0-9a-zA-Z\\_]+)', lambda m: f'∑{to_sub(m.group(1))}^{m.group(2)} ', s)

    # Защищаем сложные степени ^{...} и индексы _{...} до того, как pylatexenc снимет скобки
    s = re.sub(r'\^\{([^}]+)\}', lambda m: to_sup(m.group(1)), s)
    s = re.sub(r'_\{([^}]+)\}', lambda m: to_sub(m.group(1)), s)

    # Одиночные греческие степени: x^\alpha -> xᵅ
    for k, v in GREEK_MATH_MAP.items():
        if k.startswith('\\') and v in SUPERSCRIPTS:
            s = s.replace('^' + k, SUPERSCRIPTS[v])
    return s


def postprocess_unicode_math(text: str) -> str:
    """Постобработка строки формулы: конвертация степеней, индексов и операторов в красивый Unicode."""
    # 1. Одиночные верхние индексы: x^3, e^x, n^4, n^α
    text = re.sub(r'([a-zA-Z0-9π\(\)])\^([0-9a-zA-Zα-ω]+)', lambda m: m.group(1) + to_sup(m.group(2)), text)
    # 1.1 Отрицательные верхние индексы: e^-nx, 10^-5, x^-1
    text = re.sub(r'([a-zA-Z0-9π\(\)])\^-([0-9a-zA-Zα-ω]+)', lambda m: m.group(1) + '⁻' + to_sup(m.group(2)), text)
    # 2. Одиночные нижние индексы: x_1, a_0, ∫_0, ∑_n=1
    text = re.sub(r'([a-zA-Z0-9∫∑∏\(\)])_([0-9a-zA-Z+=]+)', lambda m: m.group(1) + to_sub(m.group(2)), text)
    # 3. Пределы интегралов и сумм
    text = text.replace('∫_0', '∫₀').replace('∫_a', '∫ₐ')
    text = re.sub(r'(\^∞)([a-zA-Z0-9(∫∑])', r'\1 \2', text)
    # 4. Пробелы вокруг знаков равенства
    text = re.sub(r'([a-zA-Zα-ωΑ-Ω0-9])=([0-9a-zA-Zα-ωΑ-Ω])', r'\1 = \2', text)
    text = re.sub(r'([a-zA-Zα-ωΑ-Ω0-9])=\s+', r'\1 = ', text)
    # 4.1 Пробелы вокруг + и - в выражениях вроде a² + b²
    text = re.sub(r'([a-zA-Z0-9⁰-⁹ᵃ-ᶻ\)])\+([a-zA-Z0-9⁰-⁹ᵃ-ᶻ\(])', r'\1 + \2', text)
    text = re.sub(r'([a-zA-Z0-9⁰-⁹ᵃ-ᶻ\)])\-([a-zA-Z0-9⁰-⁹ᵃ-ᶻ\(])', r'\1 - \2', text)
    # 5. Умножение
    text = text.replace(' * ', ' · ')
    # 5.1 Пробелы для функций: sinx -> sin x, cosbx -> cos bx
    text = re.sub(r'\b(sin|cos|tg|ctg|ln|log|exp|arcsin|arccos|arctg)([a-zA-Z0-9]+)\b', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z0-9])·(cos|sin|tg|ctg|ln|log|exp)\b', r'\1 \2', text)
    # 6. Лишние пробелы
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def convert_latex_math(text: str) -> str:
    """
    Преобразует математические выражения и формулы LaTeX в красивый, человекочитаемый Unicode.
    Использует проверенную библиотеку pylatexenc для синтаксического анализа формул
    в сочетании с умной постобработкой степеней, индексов и дробей.
    """
    if not text:
        return ""
    pre = preprocess_latex(text.strip())
    try:
        converted = _latex_converter.latex_to_text(pre)
    except Exception as e:
        logger.debug(f"Ошибка при разборе LaTeX через pylatexenc: {e}")
        converted = pre
    return postprocess_unicode_math(converted)


def strip_md_wrapping(s: str) -> str:
    """Очищает текст от внешних звездочек и подчеркиваний жирного/курсива."""
    s = s.strip()
    s = re.sub(r'^\*\*(.*?)\*\*$', r'\1', s).strip()
    s = re.sub(r'^__(.*?)__$', r'\1', s).strip()
    return s


def is_index_cell(val: str, header: str = "") -> bool:
    """Проверяет, является ли ячейка порядковым номером, ID или маркером списка."""
    clean = strip_md_wrapping(val).strip().rstrip(".)")
    h_lower = header.lower().strip()
    if h_lower in {"№", "#", "n", "n°", "номер", "item", "id", "count", "п/п", "№ п/п", "index"}:
        return True
    if clean.isdigit():
        return True
    if clean.lower() in {"последнее", "итог", "всего"}:
        return True
    return False


def convert_markdown_tables(text: str) -> str:
    """
    Интеллектуально преобразует Markdown-таблицы в аккуратный, структурированный и компактный вид для Telegram:
    - Преобразует строки в читаемые пункты списков без вертикальных палочек (|).
    - Форматирует параметры в одну строку: «1. **Имя** (период/цена) — описание/примечание».
    - Не допускает раздувания одной строки таблицы в громоздкие многострочные подпункты.
    - Двухколоночные таблицы преобразует в «• **Параметр:** Значение».
    """
    lines = text.split("\n")
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and line.strip().endswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i].strip())
                i += 1

            if len(table_lines) >= 2:
                parsed_rows = []
                for t_line in table_lines:
                    clean = t_line.strip("|")
                    cells = [strip_md_wrapping(c) for c in clean.split("|")]
                    if all(re.match(r'^:?-+:?$', c) for c in cells if c):
                        continue
                    if any(cells):
                        parsed_rows.append(cells)

                if parsed_rows:
                    headers = [h for h in parsed_rows[0]]
                    data_rows = parsed_rows[1:]

                    first_header = headers[0] if headers else ""
                    has_index_col = (
                        is_index_cell("", first_header) or
                        (len(data_rows) > 0 and sum(1 for r in data_rows if r and is_index_cell(r[0], first_header)) >= len(data_rows) * 0.5)
                    )

                    formatted_items = []
                    for row in data_rows:
                        if not any(row):
                            continue

                        # Игнорируем строки-заполнители, если в них только точки или прочерки
                        if all(c in {"…", "...", "—", "-", ""} for c in row):
                            continue

                        # Определяем индекс, заголовок и оставшиеся колонки
                        if has_index_col and len(row) > 1:
                            raw_idx = row[0].strip().rstrip(".)")
                            num = f"{raw_idx}. " if raw_idx.isdigit() else "• "
                            title = row[1].strip()
                            rem_cols = row[2:]
                            rem_headers = headers[2:] if len(headers) > 2 else []
                        elif len(row) == 2:
                            k, v = row[0].strip(), row[1].strip()
                            formatted_items.append(f"• **{k}:** {v}")
                            continue
                        else:
                            num = "• "
                            title = row[0].strip()
                            rem_cols = row[1:]
                            rem_headers = headers[1:] if len(headers) > 1 else []

                        if not title or title in {"…", "..."}:
                            continue

                        meta_val = None
                        note_val = None
                        other_parts = []

                        for c_idx, val in enumerate(rem_cols):
                            val = val.strip()
                            if not val or val == "-":
                                continue
                            h_name = rem_headers[c_idx].strip() if c_idx < len(rem_headers) else ""
                            h_lower = h_name.lower()

                            is_meta = any(k in h_lower for k in ["год", "период", "дат", "время", "срок", "цена", "стоимост", "date", "year", "price"])
                            is_note = any(k in h_lower for k in ["примечани", "описани", "детал", "комментар", "суть", "note", "desc", "comment"])

                            if is_meta and not meta_val and len(val) < 45:
                                meta_val = val
                            elif is_note and not note_val:
                                note_val = val
                            else:
                                if h_name and not is_meta and not is_note:
                                    other_parts.append(f"{h_name}: {val}")
                                else:
                                    other_parts.append(val)

                        if title.startswith(('XXMATH', '<tg-math', '$', '\\')):
                            lead = f"{num}{title}"
                        else:
                            lead = f"{num}**{title}**"
                        if meta_val:
                            lead += f" ({meta_val})"

                        if note_val and not other_parts:
                            if len(note_val) > 75:
                                formatted_items.append(f"{lead}\n   ↳ {note_val}")
                            else:
                                formatted_items.append(f"{lead} — {note_val}")
                        elif other_parts:
                            tail = " · ".join(other_parts)
                            if note_val:
                                tail += f" — {note_val}"
                            if len(tail) > 75:
                                formatted_items.append(f"{lead}\n   ↳ {tail}")
                            else:
                                formatted_items.append(f"{lead} — {tail}")
                        else:
                            formatted_items.append(lead)

                    new_lines.append("\n".join(formatted_items))
                    continue
            else:
                new_lines.extend(table_lines)
                continue
        else:
            new_lines.append(line)
            i += 1

    return "\n".join(new_lines)


def fix_squished_bullets(text: str) -> str:
    """
    Разделяет слипшиеся пункты списков в одну строку (например: «Заголовок • пункт 1 • пункт 2»)
    на отдельные строки, сохраняя структуру списков Telegram.
    При этом не разбивает компактную строку источников в конце сообщения.
    """
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        line.strip()
        # Если строка источников приклеена к концу списка через точку:
        m = re.search(r'(\s*•\s*)?(🔗\s*(?:\*\*)?Источники:.*)', line)
        if m and line.strip() != m.group(0).strip():
            content_part = line[:m.start()].strip()
            sources_part = m.group(2).strip()
            if content_part:
                new_lines.append(fix_squished_bullets(content_part))
            new_lines.append(sources_part)
            continue

        if ' • ' in line:
            parts = line.split(' • ')
            if len(parts) > 1:
                first = parts[0].strip()
                res = []
                if first:
                    if not first.endswith((':', '.', '!', '?')):
                        first += ':'
                    res.append(first)
                for p in parts[1:]:
                    p_clean = p.strip()
                    if p_clean:
                        res.append(f"• {p_clean}")
                new_lines.append('\n'.join(res))
                continue
        new_lines.append(line)
    return '\n'.join(new_lines)


def parse_balanced_braces(s: str, start_idx: int):
    """Находит индекс закрывающей фигурной скобки для скобки на start_idx с учетом вложенности."""
    if start_idx >= len(s) or s[start_idx] != '{':
        return None
    depth = 0
    for i in range(start_idx, len(s)):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return None


def convert_all_fracs(text: str) -> str:
    """Рекурсивно находит и преобразует все \\frac{A}{B} в формат (A) / (B)."""
    while r'\frac{' in text:
        idx = text.find(r'\frac{')
        num_start = idx + 5
        num_end = parse_balanced_braces(text, num_start)
        if num_end is None:
            break
        num = text[num_start + 1:num_end]
        den_start = num_end + 1
        while den_start < len(text) and text[den_start].isspace():
            den_start += 1
        if den_start >= len(text) or text[den_start] != '{':
            break
        den_end = parse_balanced_braces(text, den_start)
        if den_end is None:
            break
        den = text[den_start + 1:den_end]

        num_conv = convert_all_fracs(num)
        den_conv = convert_all_fracs(den)
        num_math = convert_latex_math(num_conv)
        den_math = convert_latex_math(den_conv)

        has_op_num = any(c in num_math for c in ['+', '-', '='])
        has_op_den = any(c in den_math for c in ['+', '-', '='])
        n_str = f"({num_math})" if has_op_num else num_math
        d_str = f"({den_math})" if has_op_den else den_math

        repl = f"{n_str} / {d_str}"
        text = text[:idx] + repl + text[den_end + 1:]
    return text


def clean_raw_latex_in_text(line: str) -> str:
    """Преобразует оставшиеся команды LaTeX в обычный красивый Unicode-текст."""
    # 1. Дроби \frac{...}{...}
    line = convert_all_fracs(line)

    # 2. Греческие буквы и математические операторы
    replacements = [
        (r'\\to\b', '→'),
        (r'->', '→'),
        (r'\\approx\b', '≈'),
        (r'\\neq\b', '≠'),
        (r'\\le\b', '≤'),
        (r'\\ge\b', '≥'),
        (r'\\pm\b', '±'),
        (r'\\times\b', '×'),
        (r'\\cdot\b', '·'),
        (r'\\tan\b', 'tg'),
        (r'\\cot\b', 'ctg'),
        (r'\\arctan\b', 'arctg'),
        (r'\\sin\b', 'sin'),
        (r'\\cos\b', 'cos'),
        (r'\\arcsin\b', 'arcsin'),
        (r'\\arccos\b', 'arccos'),
        (r'\\ln\b', 'ln'),
        (r'\\log\b', 'log'),
        (r'\\exp\b', 'exp'),
        (r'\\zeta\b', 'ζ'),
        (r'\\theta\b', 'θ'),
        (r'\\pi\b', 'π'),
        (r'\\infty\b', '∞'),
        (r'\\alpha\b', 'α'),
        (r'\\beta\b', 'β'),
        (r'\\gamma\b', 'γ'),
        (r'\\delta\b', 'δ'),
        (r'\\lambda\b', 'λ'),
        (r'\\mu\b', 'μ'),
        (r'\\sigma\b', 'σ'),
        (r'\\phi\b', 'φ'),
        (r'\\omega\b', 'ω'),
        (r'\\sqrt\{([^}]+)\}', r'√(\1)'),
    ]
    for pattern, repl in replacements:
        line = re.sub(pattern, repl, line)

    # 3. Степени: a^{2} -> a², x^2 -> x², e^{ax} -> eᵃˣ
    line = re.sub(r'\^\{([^}]+)\}', lambda m: to_sup(m.group(1)), line)
    line = re.sub(r'([a-zA-Z0-9π\(\)])\^([0-9a-zA-Zα-ω]+)', lambda m: m.group(1) + to_sup(m.group(2)), line)
    # 4. Индексы: x_{1} -> x₁, x_1 -> x₁
    line = re.sub(r'_\{([^}]+)\}', lambda m: to_sub(m.group(1)), line)
    line = re.sub(r'([a-zA-Z0-9\(\)])_([0-9a-zA-Z]+)', lambda m: m.group(1) + to_sub(m.group(2)), line)

    # 4.1 Пробелы вокруг + и -: a²+b² -> a² + b²
    line = re.sub(r'([a-zA-Z0-9⁰-⁹ᵃ-ᶻ\)])\+([a-zA-Z0-9⁰-⁹ᵃ-ᶻ\(])', r'\1 + \2', line)
    line = re.sub(r'([a-zA-Z0-9⁰-⁹ᵃ-ᶻ\)])\-([a-zA-Z0-9⁰-⁹ᵃ-ᶻ\(])', r'\1 - \2', line)

    # 5. Пробелы в функциях
    line = re.sub(r'\b(sin|cos|tg|ctg|ln|log|exp|arcsin|arccos|arctg)([a-zA-Z0-9]+)\b', r'\1 \2', line)
    line = re.sub(r'([a-zA-Z0-9])·(cos|sin|tg|ctg|ln|log|exp)\b', r'\1 \2', line)
    return line


def md_to_telegram_html(text: str) -> str:
    """
    Конвертирует Markdown и математику в валидный, красивый HTML для Telegram:
    - Разделяет склеенные в одну строку списки на аккуратные пункты.
    - Преобразует Markdown-таблицы в аккуратные списки без палочек.
    - Блоки формул и вычислений преобразует в аккуратные цитаты <blockquote><b>...</b></blockquote>.
    - Всю математическую нотацию (LaTeX, степени, корни, индексы) переводит в чистый Unicode.
    - Блоки настоящего программного кода оформляет в <pre><code class="language-...">.
    - Сохраняет уже имеющиеся валидные HTML-теги и экранирует спецсимволы.
    """
    if not text:
        return ""

    # 0. Исправляем склеенные в одну строку пункты списков (если модель ошиблась)
    text = fix_squished_bullets(text)

    # 0.1 Преобразуем неудобочитаемые таблицы Markdown в красивые списки
    text = convert_markdown_tables(text)

    code_blocks = []
    inline_codes = []
    math_blocks = []
    math_inlines = []

    # 1. Выделяем блоки математики в тройных кавычках: ```latex ... ``` или ```math ... ```
    def save_math_code_block(m):
        raw_inner = m.group(1).strip()
        conv = convert_latex_math(raw_inner)
        math_blocks.append(conv)
        return f"\nXXMATHBLOCK{len(math_blocks)-1}XX\n"

    text = re.sub(r'```(?:latex|math)\n?([\s\S]*?)```', save_math_code_block, text)

    # 2. Сохраняем обычные блоки кода программирования (python, bash, sql, etc.)
    def save_code_block(m):
        code_blocks.append(m.group(0))
        return f"XXCODEBLOCK{len(code_blocks)-1}XX"

    text = re.sub(r'```(?:[a-zA-Z0-9_\-]+)?\n?[\s\S]*?```', save_code_block, text)

    # 3. Сохраняем инлайн код программирования `...`
    def save_inline_code(m):
        inline_codes.append(m.group(0))
        return f"XXINLINECODE{len(inline_codes)-1}XX"

    text = re.sub(r'`[^`\n]+`', save_inline_code, text)

    # 3.1 Нормализуем неполный Unicode интеграл с LaTeX слешем (∫\ln -> \int \ln)
    text = re.sub(r'∫\s*\\', r'\\int \\', text)

    # 3.2 Формулы в двойных звездочках (**\frac{...}{...}** или **\int ...**) переводим в жирный Unicode
    def clean_bold_math(m):
        inner = m.group(1).strip()
        if '\\' in inner and any(k in inner for k in ['frac', 'int', 'sum', 'prod', 'sqrt', 'sin', 'cos', 'dx', 'zeta', 'lim']):
            conv = convert_latex_math(inner)
            math_inlines.append(conv)
            return f"XXMATHINLINE{len(math_inlines)-1}XX"
        return m.group(0)

    text = re.sub(r'\*\*\s*([^\n*]+?)\s*\*\*', clean_bold_math, text)

    # 3.3 Если пункт списка начинается с формулы LaTeX без тега:
    # • \frac{...}{...} (пояснение) -> • <b>(формула в Unicode)</b> (пояснение)
    def clean_bullet_math(m):
        bullet = m.group(1)
        formula = m.group(2).strip()
        conv = convert_latex_math(formula)
        math_inlines.append(conv)
        return f"{bullet}XXMATHINLINE{len(math_inlines)-1}XX"

    text = re.sub(
        r'^[ \t]*([•\-\*]\s*)(\\(?:int|iint|iiint|sum|prod|sqrt|frac|boxed|zeta)\b.+?)(?=\s*(?:[—–\-:]|\([а-яА-ЯёЁ]|[а-яА-ЯёЁ]|$))',
        clean_bullet_math,
        text,
        flags=re.MULTILINE
    )

    # 4. Блочные формулы: <tg-math-block>, $$ ... $$ и \[ ... \] -> преобразуем в блоки цитат Telegram
    def save_display_math(m):
        raw_inner = m.group(1).strip()
        conv = convert_latex_math(raw_inner)
        math_blocks.append(conv)
        return f"\nXXMATHBLOCK{len(math_blocks)-1}XX\n"

    text = re.sub(r'<tg-math-block>([\s\S]*?)</tg-math-block>', save_display_math, text, flags=re.IGNORECASE)
    text = re.sub(r'\$\$([\s\S]*?)\$\$', save_display_math, text)
    text = re.sub(r'\\\[([\s\S]*?)\\\]', save_display_math, text)

    # 5. Инлайн формулы: <tg-math>, $ ... $ и \( ... \) -> преобразуем в жирный Unicode
    def save_inline_math(m):
        raw_inner = m.group(1).strip()
        conv = convert_latex_math(raw_inner)
        math_inlines.append(conv)
        return f"XXMATHINLINE{len(math_inlines)-1}XX"

    text = re.sub(r'<tg-math>([\s\S]*?)</tg-math>', save_inline_math, text, flags=re.IGNORECASE)
    text = re.sub(r'(?<!\$)\$(?!\$)([^$\n]+)(?<!\$)\$(?!\$)', save_inline_math, text)
    text = re.sub(r'\\\((.+?)\\\)', save_inline_math, text)

    # 5.1 Обрабатываем строки с явными формулами LaTeX (\int, \frac, \sum, \sqrt, \zeta, \boxed),
    # если вся строка состоит чисто из формулы
    def save_unwrapped_math_line(m):
        raw_line = m.group(0).strip()
        if re.search(r'[а-яА-ЯёЁ]', raw_line) or re.match(r'^[•\-\*]\s+', raw_line):
            return m.group(0)
        conv = convert_latex_math(raw_line)
        math_blocks.append(conv)
        return f"\nXXMATHBLOCK{len(math_blocks)-1}XX\n"

    text = re.sub(
        r'^[ \t]*([a-zA-Z0-9_\(\)]+\s*=\s*)?\\(?:frac|int|iint|iiint|sum|prod|sqrt|boxed|zeta)[^\n]*$',
        save_unwrapped_math_line,
        text,
        flags=re.MULTILINE
    )

    # 5.2 Очищаем любые оставшиеся команды LaTeX в обычном тексте (\frac, \to, \tan, etc.)
    lines = [clean_raw_latex_in_text(l) for l in text.split('\n')]
    text = '\n'.join(lines)

    # 6. Сохраняем УЖЕ существующие валидные Telegram HTML теги (<b>, </b>, <i>, </i>, <code>, </code>, <blockquote>, </blockquote>, <a>, </a>)
    valid_tags = []
    def save_valid_tag(m):
        valid_tags.append(m.group(0))
        return f"XXVALIDTAG{len(valid_tags)-1}XX"

    text = re.sub(r'</?(?:b|i|u|s|code|pre|blockquote|a|tg-emoji)(?:\s+[^>]*?)?>', save_valid_tag, text, flags=re.IGNORECASE)

    # 7. Безопасно экранируем HTML символы (<, >, &) в оставшемся обычном тексте
    text = py_html.escape(text, quote=False)

    # 7.1 Преобразуем ссылки Markdown [текст](url) в кликабельные Telegram ссылки <a href="url">текст</a>
    def convert_md_link(m):
        link_text = m.group(1).strip()
        link_url = m.group(2).strip()
        return f'<a href="{link_url}">{link_text}</a>'

    text = re.sub(r'\[([^\]\n]+)\]\((https?://[^\s\)]+)\)', convert_md_link, text)

    # 8. Заголовки (#, ##, ###)
    text = re.sub(r'^[ \t]*#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # 9. Жирный + курсив (***текст***)
    text = re.sub(r'\*\*\*([^\n*]+?)\*\*\*', r'<b><i>\1</i></b>', text)

    # 10. Жирный текст (**жирный** или __жирный__)
    text = re.sub(r'\*\*([^\n*]+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__([^\n_]+?)__', r'<b>\1</b>', text)

    # 11. Курсив (*курсив* или _курсив_) - не триггерится внутри snake_case идентификаторов
    text = re.sub(r'(?<!\*)\*([^\n*]+?)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'(?<![a-zA-Z0-9_])_([^\n_]+?)_(?![a-zA-Z0-9_])', r'<i>\1</i>', text)

    # 12. Цитаты (> цитата или &gt; цитата)
    text = re.sub(r'^[ \t]*(?:>|&gt;)\s*(.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)

    # 13. Восстанавливаем сохраненные исходные валидные HTML теги
    def restore_valid_tag(m):
        idx = int(m.group(1))
        return valid_tags[idx]

    text = re.sub(r'XXVALIDTAG(\d+)XX', restore_valid_tag, text)

    # 14. Восстанавливаем блоки формул в виде красивых Telegram blockquote
    def restore_math_block(m):
        idx = int(m.group(1))
        content = py_html.escape(math_blocks[idx], quote=False)
        return f"<blockquote><b>{content}</b></blockquote>"

    text = re.sub(r'XXMATHBLOCK(\d+)XX', restore_math_block, text)

    # 15. Восстанавливаем инлайн формулы в виде жирного Unicode
    def restore_math_inline(m):
        idx = int(m.group(1))
        content = py_html.escape(math_inlines[idx], quote=False)
        return f"<b>{content}</b>"

    text = re.sub(r'XXMATHINLINE(\d+)XX', restore_math_inline, text)

    # 16. Восстанавливаем блоки программного кода
    def restore_code_block(m):
        idx = int(m.group(1))
        raw = code_blocks[idx]
        lang_match = re.match(r'```([a-zA-Z0-9_\-]+)?\n?([\s\S]*?)```', raw)
        lang = lang_match.group(1).strip() if lang_match and lang_match.group(1) else ""
        code_content = lang_match.group(2) if lang_match else raw[3:-3]
        code_esc = py_html.escape(code_content.strip(), quote=False)
        if lang:
            return f'<pre><code class="language-{lang}">{code_esc}</code></pre>'
        return f'<pre>{code_esc}</pre>'

    text = re.sub(r'XXCODEBLOCK(\d+)XX', restore_code_block, text)

    # 17. Восстанавливаем инлайн код программирования `...`
    def restore_inline_code(m):
        idx = int(m.group(1))
        raw = inline_codes[idx]
        code_esc = py_html.escape(raw[1:-1], quote=False)
        return f'<code>{code_esc}</code>'

    text = re.sub(r'XXINLINECODE(\d+)XX', restore_inline_code, text)

    # 18. Нормализуем пустые строки
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def convert_rich_tags_to_unicode(html_text: str) -> str:
    """Резервная функция для конвертации тегов Rich Message в Unicode HTML."""
    def replace_block(m):
        raw = m.group(1).strip()
        is_boxed = r'\boxed{' in raw or r'\boxed ' in raw
        conv = convert_latex_math(raw)
        conv_esc = py_html.escape(conv, quote=False)
        if is_boxed:
            return f"<blockquote><b>{conv_esc}</b></blockquote>"
        return f"<b>{conv_esc}</b>"

    def replace_inline(m):
        raw = m.group(1).strip()
        conv = convert_latex_math(raw)
        conv_esc = py_html.escape(conv, quote=False)
        return f"<b>{conv_esc}</b>"

    res = re.sub(r'<tg-math-block>([\s\S]*?)</tg-math-block>', replace_block, html_text, flags=re.IGNORECASE)
    res = re.sub(r'<tg-math>([\s\S]*?)</tg-math>', replace_inline, res, flags=re.IGNORECASE)
    return res


def split_telegram_chunks(text: str, max_chunk_size: int = 3800) -> list[str]:
    """Разбивает длинный текст на части с сохранением целостности строк/абзацев."""
    if len(text) <= max_chunk_size:
        return [text]

    chunks = []
    lines = text.split("\n")
    current_chunk = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chunk_size and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = line_len
        else:
            current_chunk.append(line)
            current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


async def send_formatted_message(message: Message, text: str, reply_markup=None):
    """
    Отправляет пользователю сообщение с красивой разметкой и формулами.
    - Разбирает ответ на текст и формулы, формулы рендерит в PNG.
    - При возникновении ошибки безопасно отправляет plain text без потери содержимого.
    - Отключает предпросмотр веб-ссылок.
    """
    if not text:
        return

    try:
        from bot.services.rich_message import send_rich_response
        await send_rich_response(
            bot=message.bot,
            chat_id=message.chat.id,
            raw_markdown=text,
            reply_markup=reply_markup
        )
        return
    except Exception as e:
        logger.warning(f"Ошибка при отправке rich message: {e}. Фолбэк на стандартную отправку...")

    # Резервная отправка через sendMessage
    raw_chunks = split_telegram_chunks(text, max_chunk_size=3200)

    for i, raw_chunk in enumerate(raw_chunks):
        is_last = (i == len(raw_chunks) - 1)
        kb = reply_markup if is_last else None
        html_chunk = md_to_telegram_html(raw_chunk)

        try:
            await message.answer(
                html_chunk,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        except Exception as e:
            logger.warning(f"Ошибка отправки сообщения в формате HTML: {e}. Отправка в plain text...")
            plain_txt = re.sub(r'</?[^>]+>', '', html_chunk)
            try:
                await message.answer(
                    plain_txt,
                    parse_mode=None,
                    reply_markup=kb,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
            except Exception:
                await message.answer(
                    raw_chunk,
                    parse_mode=None,
                    reply_markup=kb,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )

