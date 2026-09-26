import re
import logging
import html as py_html
from typing import Dict, Any, List
from aiogram import html
from aiogram.enums import ParseMode
from aiogram.types import Message, LinkPreviewOptions

from bot.database.models import FuelLog, ServiceLog, ItemLocation
from bot.emojis import (
    E_DROP,
    E_WRENCH,
    E_BOX,
    E_CHART,
    E_SEARCH,
    E_BULB,
    E_LOCATION,
    E_VOICE_TEXT
)

logger = logging.getLogger(__name__)


def format_fuel_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку подтверждения заправки с expandable blockquote."""
    liters = data.get("liters", 0.0)
    cost = data.get("cost", 0.0)
    odometer = data.get("odometer", 0)
    station = data.get("station_name") or "Не указана"

    price_per_l = round(cost / liters, 2) if liters and cost else 0.0

    lines = [
        f"{E_DROP} <b>Распознана заправка автомобиля</b>\n",
        f"• <b>Литры:</b> <code>{liters:.1f} л</code>",
        f"• <b>Стоимость:</b> <code>{cost:,.2f} ₽</code>",
        f"• <b>Цена за литр:</b> <code>{price_per_l:.2f} ₽</code>",
        f"• <b>Пробег на одометре:</b> <code>{odometer:,} км</code>".replace(",", " "),
        f"• <b>АЗС:</b> <i>{html.quote(str(station))}</i>\n"
    ]

    if raw_text:
        lines.append(f"<blockquote expandable>{E_VOICE_TEXT} <b>Исходный текст:</b>\n{html.quote(raw_text)}</blockquote>\n")

    lines.append("<i>Подтвердите сохранение записи в журнал:</i>")
    return "\n".join(lines)


def format_service_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку подтверждения ТО / ремонта."""
    title = data.get("title", "Техническое обслуживание")
    cost = data.get("cost")
    odometer = data.get("odometer", 0)
    notes = data.get("notes")

    lines = [
        f"{E_WRENCH} <b>Распознано сервисное обслуживание / ремонт</b>\n",
        f"• <b>Работа / Деталь:</b> <b>{html.quote(str(title))}</b>",
        f"• <b>Пробег:</b> <code>{odometer:,} км</code>".replace(",", " "),
    ]

    if cost is not None:
        lines.append(f"• <b>Стоимость:</b> <code>{cost:,.2f} ₽</code>")
    if notes:
        lines.append(f"• <b>Заметки:</b> <i>{html.quote(str(notes))}</i>")

    lines.append("")
    if raw_text:
        lines.append(f"<blockquote expandable>{E_VOICE_TEXT} <b>Исходный текст:</b>\n{html.quote(raw_text)}</blockquote>\n")

    lines.append("<i>Подтвердите сохранение записи в журнал:</i>")
    return "\n".join(lines)


def format_location_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку сохранения местоположения вещи."""
    item_name = data.get("item_name", "Вещь")
    location = data.get("location", "Гараж")

    lines = [
        f"{E_BOX} <b>Запись в инвентарь гаража/дачи</b>\n",
        f"• <b>Предмет:</b> <b>{html.quote(str(item_name))}</b>",
        f"• <b>Место хранения:</b> <code>{html.quote(str(location))}</code>\n"
    ]

    if raw_text:
        lines.append(f"<blockquote expandable>{E_VOICE_TEXT} <b>Исходный текст:</b>\n{html.quote(raw_text)}</blockquote>\n")

    lines.append("<i>Запомнить это место?</i>")
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
        lines.append(
            f"• <b>{date_str}</b>{station_str}: "
            f"<code>{it.liters:.1f} л</code> на <code>{it.cost:,.0f} ₽</code> | "
            f"<code>{it.odometer:,} км</code>".replace(",", " ")
        )
    return "\n".join(lines)


def format_service_history(logs: List[ServiceLog]) -> str:
    """Форматирует историю ТО."""
    if not logs:
        return f"{E_WRENCH} История обслуживания и ремонтов пока пуста."

    lines = [f"{E_WRENCH} <b>Последние записи ТО и сервиса:</b>\n"]
    for it in logs:
        date_str = it.date.strftime("%d.%m.%Y")
        cost_str = f" на <code>{it.cost:,.0f} ₽</code>" if it.cost else ""
        lines.append(
            f"• <b>{date_str}</b>: <b>{html.quote(it.title)}</b>{cost_str} | "
            f"<code>{it.odometer:,} км</code>".replace(",", " ")
        )
    return "\n".join(lines)


def format_stats_summary(fuel_stats: Dict[str, Any]) -> str:
    """Форматирует общую статистику по расходам."""
    total_liters = fuel_stats.get("total_liters", 0.0)
    total_cost = fuel_stats.get("total_cost", 0.0)
    avg_price = fuel_stats.get("avg_price", 0.0)
    avg_consumption = fuel_stats.get("avg_consumption", 0.0)

    lines = [
        f"{E_CHART} <b>Сводка расходов на топливо:</b>\n",
        f"• <b>Всего заправлено:</b> <code>{total_liters:.1f} л</code>",
        f"• <b>Общие затраты:</b> <code>{total_cost:,.2f} ₽</code>",
        f"• <b>Средняя цена за литр:</b> <code>{avg_price:.2f} ₽</code>",
    ]
    if avg_consumption > 0:
        lines.append(f"• <b>Средний расход:</b> <code>{avg_consumption:.1f} л / 100 км</code>")
    return "\n".join(lines)

from pylatexenc.latex2text import LatexNodes2Text, get_default_latex_context_db, MacroTextSpec

# Настройка парсера LaTeX в Unicode
_latex_db = get_default_latex_context_db()

def _frac_repl(node, l2tobj):
    num = l2tobj.nodelist_to_text([node.nodeargs[0]]).strip()
    den = l2tobj.nodelist_to_text([node.nodeargs[1]]).strip()
    has_op_num = any(c in num for c in ['+', '-', '=', ' ', '·', '×'])
    has_op_den = any(c in den for c in ['+', '-', '=', ' ', '·', '×'])
    n_str = f'({num})' if has_op_num else num
    d_str = f'({den})' if has_op_den else den
    return f'{n_str} / {d_str}'

def _sqrt_repl(node, l2tobj):
    inner = l2tobj.nodelist_to_text([node.nodeargs[0]]).strip()
    if len(inner) <= 3 and not any(op in inner for op in '+-*/±= '):
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
    'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ', 'd': 'ᵈ', 'e': 'ᵉ',
    'f': 'ᶠ', 'g': 'ᵍ', 'h': 'ʰ', 'i': 'ⁱ', 'j': 'ʲ',
    'k': 'ᵏ', 'l': 'ˡ', 'm': 'ᵐ', 'n': 'ⁿ', 'o': 'ᵒ',
    'p': 'ᵖ', 'r': 'ʳ', 's': 'ˢ', 't': 'ᵗ', 'u': 'ᵘ',
    'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ', 'y': 'ʸ', 'z': 'ᶻ',
    'A': 'ᴬ', 'B': 'ᴮ', 'D': 'ᴰ', 'E': 'ᴱ', 'G': 'ᴳ',
    'H': 'ᴴ', 'I': 'ᴵ', 'J': 'ᴶ', 'K': 'ᴷ', 'L': 'ᴸ',
    'M': 'ᴹ', 'N': 'ᴺ', 'O': 'ᴼ', 'P': 'ᴾ', 'R': 'ᴿ',
    'T': 'ᵀ', 'U': 'ᵁ', 'W': 'ᵂ',
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


def to_sup(text: str) -> str:
    """Конвертирует строку в надстрочные символы Unicode."""
    return "".join(SUPERSCRIPTS.get(c, c) for c in text)


def to_sub(text: str) -> str:
    """Конвертирует строку в подстрочные символы Unicode."""
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
    s = re.sub(r'\\[,;!]', ' ', s)
    return s


def postprocess_unicode_math(text: str) -> str:
    """Постобработка строки формулы: конвертация степеней, индексов и операторов в красивый Unicode."""
    # 1. Верхние индексы ^{...}
    text = re.sub(r'\^\{([^}]+)\}', lambda m: to_sup(m.group(1)), text)
    # 2. Одиночные верхние индексы: x^3, e^x, n^4 (без + и -, чтобы не поглощать e^x-1)
    text = re.sub(r'([a-zA-Z0-9π\(\)])\^([0-9a-zA-Z]+)', lambda m: m.group(1) + to_sup(m.group(2)), text)
    # 2.1 Отрицательные верхние индексы: e^-nx, 10^-5, x^-1
    text = re.sub(r'([a-zA-Z0-9π\(\)])\^-([0-9a-zA-Z]+)', lambda m: m.group(1) + '⁻' + to_sup(m.group(2)), text)
    # 3. Нижние индексы _{...}
    text = re.sub(r'_\{([^}]+)\}', lambda m: to_sub(m.group(1)), text)
    # 4. Одиночные нижние индексы: x_1, a_0, ∫_0, ∑_n=1
    text = re.sub(r'([a-zA-Z0-9∫∑∏\(\)])_([0-9a-zA-Z+=]+)', lambda m: m.group(1) + to_sub(m.group(2)), text)
    # 5. Пределы интегралов
    text = text.replace('∫_0', '∫₀').replace('∫_a', '∫ₐ')
    # 6. Умножение
    text = text.replace(' * ', ' · ')
    # 7. Лишние пробелы
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


def md_to_telegram_html(text: str) -> str:
    """
    Конвертирует Markdown и математику в валидный, красивый HTML для Telegram:
    - Преобразует Markdown-таблицы в аккуратные списки без палочек.
    - Блоки формул и вычислений преобразует в аккуратные цитаты <blockquote><b>...</b></blockquote>.
    - Всю математическую нотацию (LaTeX, степени, корни, индексы) переводит в Unicode внутри формул.
    - Блоки настоящего программного кода (python, bash, js и т.д.) оформляет в <pre><code class="language-...">.
    - Сохраняет уже имеющиеся валидные HTML-теги и экранирует спецсимволы.
    """
    if not text:
        return ""

    # 0. Преобразуем неудобочитаемые таблицы Markdown в красивые списки
    text = convert_markdown_tables(text)

    code_blocks = []
    inline_codes = []
    math_blocks = []
    math_inlines = []

    # 1. Выделяем блоки математики в тройных кавычках: ```latex ... ``` или ```math ... ```
    def save_math_code_block(m):
        raw_inner = m.group(1).strip()
        converted = convert_latex_math(raw_inner)
        math_blocks.append(converted)
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

    # 4. Блочные формулы: $$ ... $$ и \[ ... \] -> преобразуем в блоки цитат Telegram
    def save_display_math(m):
        raw_inner = m.group(1).strip()
        converted = convert_latex_math(raw_inner)
        math_blocks.append(converted)
        return f"\nXXMATHBLOCK{len(math_blocks)-1}XX\n"

    text = re.sub(r'\$\$([\s\S]*?)\$\$', save_display_math, text)
    text = re.sub(r'\\\[([\s\S]*?)\\\]', save_display_math, text)

    # 5. Инлайн формулы: $ ... $ и \( ... \) -> преобразуем в жирный Unicode
    def save_inline_math(m):
        raw_inner = m.group(1).strip()
        converted = convert_latex_math(raw_inner)
        math_inlines.append(converted)
        return f"XXMATHINLINE{len(math_inlines)-1}XX"

    text = re.sub(r'(?<!\$)\$(?!\$)([^$\n]+)(?<!\$)\$(?!\$)', save_inline_math, text)
    text = re.sub(r'\\\((.+?)\\\)', save_inline_math, text)

    # 5.1 Обрабатываем строки с явными формулами LaTeX (\int, \frac, \sum, \sqrt, \zeta, \boxed), если они не были обернуты в $$ или $
    STANDALONE_MATH_RE = re.compile(
        r'^[ \t]*(?:[a-zA-Z0-9_\(\)]+\s*=\s*)?\\(?:frac|int|iint|iiint|sum|prod|sqrt|boxed|zeta)(?![a-zA-Z])'
    )

    def save_unwrapped_math_line(m):
        raw_line = m.group(0).strip()
        if STANDALONE_MATH_RE.match(raw_line):
            converted = convert_latex_math(raw_line)
            math_blocks.append(converted)
            return f"\nXXMATHBLOCK{len(math_blocks)-1}XX\n"
        return convert_latex_math(raw_line)

    text = re.sub(
        r'^[ \t]*([^\n]*?\\(?:frac|int|iint|iiint|sum|prod|sqrt|boxed|zeta|alpha|beta|gamma|delta|pi|infty)(?![a-zA-Z])[^\n]*)$',
        save_unwrapped_math_line,
        text,
        flags=re.MULTILINE
    )

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

    # 12. Восстанавливаем блоки формул в виде Telegram blockquote
    def restore_math_block(m):
        idx = int(m.group(1))
        content = py_html.escape(math_blocks[idx], quote=False)
        return f"<blockquote><b>{content}</b></blockquote>"

    text = re.sub(r'XXMATHBLOCK(\d+)XX', restore_math_block, text)

    # 13. Восстанавливаем инлайн формулы
    def restore_math_inline(m):
        idx = int(m.group(1))
        content = py_html.escape(math_inlines[idx], quote=False)
        return f"<b>{content}</b>"

    text = re.sub(r'XXMATHINLINE(\d+)XX', restore_math_inline, text)

    # 14. Восстанавливаем блоки программного кода
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

    # 15. Восстанавливаем инлайн код программирования `...`
    def restore_inline_code(m):
        idx = int(m.group(1))
        raw = inline_codes[idx]
        code_esc = py_html.escape(raw[1:-1], quote=False)
        return f'<code>{code_esc}</code>'

    text = re.sub(r'XXINLINECODE(\d+)XX', restore_inline_code, text)

    # 16. Нормализуем пустые строки
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


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
    - Разбивает исходный текст на части с сохранением структуры строк и абзацев ДО конвертации в HTML.
    - Это гарантирует, что теги <blockquote>, <b>, <pre> никогда не окажутся разорванными между двумя сообщениями.
    - Отключает предпросмотр ссылок (link previews).
    """
    if not text:
        return

    # Разбиваем исходный текст с запасом по размеру (3200 символов), чтобы после HTML-тегов не превысить 4096
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
            await message.answer(
                raw_chunk,
                parse_mode=None,
                reply_markup=kb,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )

