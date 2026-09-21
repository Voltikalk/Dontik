import re
import logging
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
    for it in logs:
        date_str = it.date.strftime("%d.%m.%Y")
        cost_str = f" — <code>{it.cost:,.0f} ₽</code>" if it.cost else ""
        lines.append(
            f"• <b>{date_str}</b> | <code>{it.odometer:,} км</code>: "
            f"<b>{html.quote(it.title)}</b>{cost_str}".replace(",", " ")
        )
    return "\n".join(lines)


def format_stats_summary(fuel_stats: Dict[str, Any]) -> str:
    """Форматирует общую статистику расходов."""
    lines = [
        "📊 <b>Сводная статистика по автомобилю:</b>\n",
        f"• <b>Всего заправок:</b> <code>{fuel_stats.get('count', 0)}</code>",
        f"• <b>Суммарный объем топлива:</b> <code>{fuel_stats.get('total_liters', 0.0)} л</code>",
        f"• <b>Всего потрачено на топливо:</b> <code>{fuel_stats.get('total_cost', 0.0):,.2f} ₽</code>",
        f"• <b>Средняя цена за литр:</b> <code>{fuel_stats.get('avg_price_per_liter', 0.0):.2f} ₽</code>",
        f"• <b>Текущий зафиксированный пробег:</b> <code>{fuel_stats.get('max_odometer', 0):,} км</code>".replace(",", " ")
    ]
    return "\n".join(lines)


def md_to_telegram_html(text: str) -> str:
    """
    Конвертирует стандартный Markdown и LaTeX формулы в валидный HTML для Telegram.
    - Защищает блоки кода ```lang ... ``` и формулы LaTeX ($$...$$, \\[...\\], $...$, \\(...\\)).
    - Экранирует HTML символы (<, >, &) в обычном тексте.
    - Преобразует заголовки (### Заголовок) в <b>Заголовок</b>.
    - Преобразует **жирный** и __жирный__ в <b>жирный</b>.
    - Преобразует *курсив* и _курсив_ в <i>курсив</i>.
    - Преобразует цитаты (> цитата) в <blockquote>цитата</blockquote>.
    - Восстанавливает блоки LaTeX в <pre><code class="language-latex">...</code></pre>.
    - Восстанавливает инлайн LaTeX и код в <code>...</code>.
    - Восстанавливает блоки кода в <pre><code class="language-...">...</code></pre>.
    """
    if not text:
        return ""

    placeholders = []

    def repl_block(m):
        placeholders.append(m.group(0))
        return f"@@BLOCK{len(placeholders)-1}BLOCK@@"

    # 1. Блоки кода ```lang\n...```
    text = re.sub(r'```(?:[a-zA-Z0-9_\-]+)?\n?[\s\S]*?```', repl_block, text)

    # 2. Блочные LaTeX формулы: $$ ... $$ и \[ ... \]
    text = re.sub(r'\$\$[\s\S]*?\$\$', repl_block, text)
    text = re.sub(r'\\\[[\s\S]*?\\\]', repl_block, text)

    # 3. Инлайн LaTeX формулы: $ ... $ и \( ... \)
    text = re.sub(r'(?<!\$)\$(?!\$)[^$\n]+(?<!\$)\$(?!\$)', repl_block, text)
    text = re.sub(r'\\\([^\n]+?\\\)', repl_block, text)

    # 4. Инлайн код `...`
    text = re.sub(r'`[^`\n]+`', repl_block, text)

    # 5. Экранируем HTML символы в обычном тексте (<, >, &)
    text = html.escape(text, quote=False)

    # 6. Заголовки (#, ##, ###)
    text = re.sub(r'^[ \t]*#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # 7. Жирный текст (**жирный** или __жирный__)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__([^_]+)__', r'<b>\1</b>', text)

    # 8. Курсив (*курсив* или _курсив_)
    text = re.sub(r'(?<!\w)\*([^*]+)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'<i>\1</i>', text)

    # 9. Цитаты (> цитата или &gt; цитата)
    text = re.sub(r'^[ \t]*(?:>|&gt;)\s*(.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)

    # 10. Восстанавливаем сохраненные блоки
    def restore_block(m):
        idx = int(m.group(1))
        raw = placeholders[idx]

        # Блочный код
        if raw.startswith("```"):
            lang_match = re.match(r'```([a-zA-Z0-9_\-]+)?\n?([\s\S]*?)```', raw)
            lang = lang_match.group(1).strip() if lang_match and lang_match.group(1) else ""
            code_content = lang_match.group(2) if lang_match else raw[3:-3]
            code_esc = html.escape(code_content.strip(), quote=False)
            if lang:
                return f'<pre><code class="language-{lang}">{code_esc}</code></pre>'
            return f'<pre>{code_esc}</pre>'

        # Блочный LaTeX $$...$$ или \[...\]
        elif raw.startswith("$$") or raw.startswith("\\["):
            body = raw[2:-2].strip()
            math_esc = html.escape(body, quote=False)
            return f'<pre><code class="language-latex">{math_esc}</code></pre>'

        # Инлайн LaTeX $...$ или \(...\)
        elif raw.startswith("$") or raw.startswith("\\("):
            body = raw[2:-2].strip() if raw.startswith("\\(") else raw[1:-1].strip()
            math_esc = html.escape(body, quote=False)
            return f'<code>{math_esc}</code>'

        # Инлайн код `...`
        elif raw.startswith("`"):
            code_esc = html.escape(raw[1:-1], quote=False)
            return f'<code>{code_esc}</code>'

        return raw

    text = re.sub(r'@@BLOCK(\d+)BLOCK@@', restore_block, text)
    return text


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

