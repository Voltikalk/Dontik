import re
import logging
import html as py_html
from typing import Dict, Any, List
from aiogram import html
from aiogram.enums import ParseMode
from aiogram.types import Message

from bot.database.models import FuelLog, ServiceLog, ItemLocation

logger = logging.getLogger(__name__)


def format_fuel_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку подтверждения заправки с expandable blockquote."""
    liters = data.get("liters", 0.0)
    cost = data.get("cost", 0.0)
    odometer = data.get("odometer", 0)
    station = data.get("station_name") or "Не указана"

    price_per_l = round(cost / liters, 2) if liters and cost else 0.0

    lines = [
        "⛽ <b>Распознана заправка автомобиля</b>\n",
        f"• <b>Литры:</b> <code>{liters:.1f} л</code>",
        f"• <b>Стоимость:</b> <code>{cost:,.2f} ₽</code>",
        f"• <b>Цена за литр:</b> <code>{price_per_l:.2f} ₽</code>",
        f"• <b>Пробег на одометре:</b> <code>{odometer:,} км</code>".replace(",", " "),
        f"• <b>АЗС:</b> <i>{html.quote(str(station))}</i>\n"
    ]

    if raw_text:
        lines.append(f"<blockquote expandable>🗣 <b>Исходный текст:</b>\n{html.quote(raw_text)}</blockquote>\n")

    lines.append("<i>Подтвердите сохранение записи в журнал:</i>")
    return "\n".join(lines)


def format_service_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку подтверждения ТО / ремонта."""
    title = data.get("title", "Техническое обслуживание")
    cost = data.get("cost")
    odometer = data.get("odometer", 0)
    notes = data.get("notes")

    lines = [
        "🔧 <b>Распознано сервисное обслуживание / ремонт</b>\n",
        f"• <b>Работа / Деталь:</b> <b>{html.quote(str(title))}</b>",
        f"• <b>Пробег:</b> <code>{odometer:,} км</code>".replace(",", " "),
    ]

    if cost is not None:
        lines.append(f"• <b>Стоимость:</b> <code>{cost:,.2f} ₽</code>")
    if notes:
        lines.append(f"• <b>Заметки:</b> <i>{html.quote(str(notes))}</i>")

    lines.append("")
    if raw_text:
        lines.append(f"<blockquote expandable>🗣 <b>Исходный текст:</b>\n{html.quote(raw_text)}</blockquote>\n")

    lines.append("<i>Подтвердите сохранение записи в журнал:</i>")
    return "\n".join(lines)


def format_location_card(data: Dict[str, Any], raw_text: str = "") -> str:
    """Форматирует карточку сохранения местоположения вещи."""
    item_name = data.get("item_name", "Вещь")
    location = data.get("location", "Гараж")

    lines = [
        "📦 <b>Запись в инвентарь гаража/дачи</b>\n",
        f"• <b>Предмет:</b> <b>{html.quote(str(item_name))}</b>",
        f"• <b>Место хранения:</b> <code>{html.quote(str(location))}</code>\n"
    ]

    if raw_text:
        lines.append(f"<blockquote expandable>🗣 <b>Исходный текст:</b>\n{html.quote(raw_text)}</blockquote>\n")

    lines.append("<i>Запомнить это место?</i>")
    return "\n".join(lines)


def format_found_items(items: List[ItemLocation], query: str) -> str:
    """Форматирует результаты поиска вещей в гараже."""
    if not items:
        return (
            f"🔍 По запросу «<b>{html.quote(query)}</b>» ничего не найдено.\n\n"
            "💡 Чтобы бот запомнил вещь, просто скажите или напишите, например:\n"
            "<i>«Положил домкрат в левый угол у ворот»</i>"
        )

    lines = [f"📍 <b>Найдено в гараже / на даче (запрос: {html.quote(query)}):</b>\n"]
    for idx, it in enumerate(items, 1):
        updated = it.updated_at.strftime("%d.%m.%Y")
        lines.append(
            f"{idx}. <b>{html.quote(it.item_name)}</b>\n"
            f"   ↳ 📍 <code>{html.quote(it.location)}</code> <i>(обновлено: {updated})</i>"
        )
    return "\n".join(lines)


def format_all_items_list(items: List[ItemLocation]) -> str:
    """Форматирует полный список вещей пользователя."""
    if not items:
        return "📦 В гараже пока ничего не записано. Скажите или напишите, что и куда вы положили!"

    lines = ["📦 <b>Список вещей на хранении:</b>\n"]
    for idx, it in enumerate(items, 1):
        lines.append(f"{idx}. <b>{html.quote(it.item_name)}</b> — <code>{html.quote(it.location)}</code>")
    lines.append("\n💡 <i>Чтобы найти конкретную вещь, спросите «Где лежит ...?»</i>")
    return "\n".join(lines)


def format_fuel_history(logs: List[FuelLog]) -> str:
    """Форматирует историю заправок."""
    if not logs:
        return "⛽ История заправок пока пуста."

    lines = ["⛽ <b>Последние заправки:</b>\n"]
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
        return "🔧 История обслуживания и ремонтов пока пуста."

    lines = ["🔧 <b>Последние записи ТО и сервиса:</b>\n"]
   # --- Словари символов Unicode для степеней и индексов ---
SUPERSCRIPTS = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
    'n': 'ⁿ', 'i': 'ⁱ', 'x': 'ˣ', 'y': 'ʸ', 'a': 'ᵃ', 'b': 'ᵇ'
}

SUBSCRIPTS = {
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
    '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
    '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
    ',': ',', ';': ';',
    'a': 'ₐ', 'e': 'ₑ', 'h': 'ₕ', 'i': 'ᵢ', 'j': 'ⱼ',
    'k': 'ₖ', 'l': 'ₗ', 'm': 'ₘ', 'n': 'ₙ', 'o': 'ₒ',
    'p': 'ₚ', 'r': 'ᵣ', 's': 'ₛ', 't': 'ₜ', 'u': 'ᵤ',
    'v': 'ᵥ', 'x': 'ₓ'
}

LATEX_SYMBOLS = [
    (r'\\pm', '±'),
    (r'\\mp', '∓'),
    (r'\\approx', '≈'),
    (r'\\sim', '~'),
    (r'\\neq', '≠'),
    (r'\\ne', '≠'),
    (r'\\leq', '≤'),
    (r'\\le', '≤'),
    (r'\\geq', '≥'),
    (r'\\ge', '≥'),
    (r'\\times', '×'),
    (r'\\cdot', '·'),
    (r'\\div', '÷'),
    (r'\\degree', '°'),
    (r'\\circ', '°'),
    (r'\\infty', '∞'),
    (r'\\in', '∈'),
    (r'\\notin', '∉'),
    (r'\\subset', '⊂'),
    (r'\\subseteq', '⊆'),
    (r'\\cup', '∪'),
    (r'\\cap', '∩'),
    (r'\\emptyset', '∅'),
    (r'\\forall', '∀'),
    (r'\\exists', '∃'),
    (r'\\to', '→'),
    (r'\\rightarrow', '→'),
    (r'\\implies', '⇒'),
    (r'\\Rightarrow', '⇒'),
    (r'\\iff', '⇔'),
    (r'\\Leftrightarrow', '⇔'),
    (r'\\alpha', 'α'),
    (r'\\beta', 'β'),
    (r'\\gamma', 'γ'),
    (r'\\delta', 'δ'),
    (r'\\epsilon', 'ε'),
    (r'\\varepsilon', 'ε'),
    (r'\\zeta', 'ζ'),
    (r'\\eta', 'η'),
    (r'\\theta', 'θ'),
    (r'\\vartheta', 'θ'),
    (r'\\iota', 'ι'),
    (r'\\kappa', 'κ'),
    (r'\\lambda', 'λ'),
    (r'\\mu', 'μ'),
    (r'\\nu', 'ν'),
    (r'\\xi', 'ξ'),
    (r'\\pi', 'π'),
    (r'\\rho', 'ρ'),
    (r'\\sigma', 'σ'),
    (r'\\tau', 'τ'),
    (r'\\phi', 'φ'),
    (r'\\varphi', 'φ'),
    (r'\\chi', 'χ'),
    (r'\\psi', 'ψ'),
    (r'\\omega', 'ω'),
    (r'\\Gamma', 'Γ'),
    (r'\\Delta', 'Δ'),
    (r'\\Theta', 'Θ'),
    (r'\\Lambda', 'Λ'),
    (r'\\Xi', 'Ξ'),
    (r'\\Pi', 'Π'),
    (r'\\Sigma', 'Σ'),
    (r'\\Phi', 'Φ'),
    (r'\\Psi', 'Ψ'),
    (r'\\Omega', 'Ω'),
    (r'\\sum', '∑'),
    (r'\\prod', '∏'),
    (r'\\int', '∫'),
    (r'\\iint', '∬'),
    (r'\\iiint', '∭'),
    (r'\\partial', '∂'),
    (r'\\nabla', '∇'),
    (r'\\left\(', '('),
    (r'\\right\)', ')'),
    (r'\\left\[', '['),
    (r'\\right\]', ']'),
    (r'\\left\\\{', '{'),
    (r'\\right\\\}', '}'),
    (r'\\\{', '{'),
    (r'\\\}', '}'),
    (r'\\quad', '  '),
    (r'\\qquad', '    '),
    (r'\\,', ' '),
    (r'\\;', ' '),
    (r'\\!', ''),
    (r'\\text\{([^}]+)\}', r'\1'),
    (r'\\mathrm\{([^}]+)\}', r'\1'),
    (r'\\mathbf\{([^}]+)\}', r'\1'),
    (r'\\boldsymbol\{([^}]+)\}', r'\1'),
]


def to_sup(text: str) -> str:
    """Конвертирует строку в надстрочные символы Unicode."""
    return "".join(SUPERSCRIPTS.get(c, c) for c in text)


def to_sub(text: str) -> str:
    """Конвертирует строку в подстрочные символы Unicode."""
    return "".join(SUBSCRIPTS.get(c, c) for c in text)


def convert_latex_math(text: str) -> str:
    """
    Преобразует математические выражения и команды LaTeX в красивый человекочитаемый Unicode.
    Пример: \\sqrt{38} -> √38, x^2 -> x², x_1 -> x₁, \\pm -> ±, \\approx -> ≈.
    """
    if not text:
        return ""

    # Замена корней \sqrt[n]{x} и \sqrt{x}
    text = re.sub(r'\\sqrt\[(\d+)\]\{([^}]+)\}', r'\1√(\2)', text)
    def repl_sqrt(m):
        inner = m.group(1).strip()
        if len(inner) <= 3 and not any(op in inner for op in '+-*/±= '):
            return f"√{inner}"
        return f"√({inner})"
    text = re.sub(r'\\sqrt\{([^}]+)\}', repl_sqrt, text)

    # Замена дробей \frac{a}{b} -> (a) / (b)
    def repl_frac(m):
        num = m.group(1).strip()
        den = m.group(2).strip()
        if len(num) <= 2 and len(den) <= 2 and not any(op in num+den for op in '+-*/±= '):
            return f"{num}/{den}"
        return f"({num}) / ({den})"
    text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', repl_frac, text)

    # Замена стандартных символов и команд
    for pattern, repl in LATEX_SYMBOLS:
        text = re.sub(pattern, repl, text)

    # Степени: ^{...} или ^x
    text = re.sub(r'\^\{([0-9a-zA-Z+-]+)\}', lambda m: to_sup(m.group(1)), text)
    text = re.sub(r'\^([0-9a-zA-Z+-])', lambda m: to_sup(m.group(1)), text)

    # Индексы: _{...} или _x
    text = re.sub(r'_\{([0-9a-zA-Z+-,;]+)\}', lambda m: to_sub(m.group(1)), text)
    text = re.sub(r'_([0-9a-zA-Z+-])', lambda m: to_sub(m.group(1)), text)

    # Убираем оставшиеся обратные слэши перед словами
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text)

    return text


def md_to_telegram_html(text: str) -> str:
    """
    Конвертирует Markdown и математику в валидный, красивый HTML для Telegram:
    - Блоки формул и вычислений преобразует в аккуратные цитаты <blockquote><b>...</b></blockquote>.
    - Всю математическую нотацию (LaTeX, степени, корни, индексы) переводит в Unicode.
    - Блоки настоящего программного кода (python, bash, js и т.д.) оформляет в <pre><code class="language-...">.
    - Обычный текст экранирует (py_html.escape) и форматирует жирным <b>, курсивом <i>, заголовками.
    """
    if not text:
        return ""

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

    # 6. Преобразуем любые оставшиеся LaTeX команды в обычном тексте (\sqrt{...}, \approx, x^2, x_1)
    text = convert_latex_math(text)

    # 7. Безопасно экранируем HTML символы (<, >, &) в оставшемся обычном тексте
    text = py_html.escape(text, quote=False)

    # 8. Заголовки (#, ##, ###)
    text = re.sub(r'^[ \t]*#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # 9. Жирный текст (**жирный** или __жирный__)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__([^_]+)__', r'<b>\1</b>', text)

    # 10. Курсив (*курсив* или _курсив_)
    text = re.sub(r'(?<!\w)\*([^*]+)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'<i>\1</i>', text)

    # 11. Цитаты (> цитата или &gt; цитата)
    text = re.sub(r'^[ \t]*(?:>|&gt;)\s*(.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)

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
    - Конвертирует Markdown и LaTeX в Telegram HTML.
    - Автоматически разбивает на сообщения, если превышен лимит 4096 символов.
    - В случае редких ошибок парсинга Telegram плавно откатывается к чистому тексту.
    """
    if not text:
        return

    html_content = md_to_telegram_html(text)
    chunks = split_telegram_chunks(html_content)

    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        kb = reply_markup if is_last else None
        try:
            await message.answer(chunk, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as e:
            logger.warning(f"Ошибка отправки сообщения в формате HTML: {e}. Отправка в plain text...")
            raw_chunks = split_telegram_chunks(text)
            raw_chunk = raw_chunks[i] if i < len(raw_chunks) else text
            await message.answer(raw_chunk, parse_mode=None, reply_markup=kb)

