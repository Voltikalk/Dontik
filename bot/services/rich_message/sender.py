import re
import html as py_html
import logging
from typing import Optional, List
from aiogram import Bot
from aiogram.types import Message, InputRichMessage
from aiogram.enums import ParseMode

from bot.services.formatters import convert_latex_math
from .converter import markdown_to_rich_html, split_rich_message

logger = logging.getLogger(__name__)


def replace_math_tags_with_unicode(rich_html: str) -> str:
    """
    Fallback converter: replaces <tg-math-block> and <tg-math> tags with
    standard Telegram blockquotes and bold Unicode text.
    Used if Telegram rejects LaTeX expressions in sendRichMessage.
    """
    def block_repl(m: re.Match) -> str:
        raw_formula = py_html.unescape(m.group(1).strip())
        conv = convert_latex_math(raw_formula)
        conv_esc = py_html.escape(conv, quote=False)
        return f"<blockquote><b>{conv_esc}</b></blockquote>"

    def inline_repl(m: re.Match) -> str:
        raw_formula = py_html.unescape(m.group(1).strip())
        conv = convert_latex_math(raw_formula)
        conv_esc = py_html.escape(conv, quote=False)
        return f"<b>{conv_esc}</b>"

    s = re.sub(r"<tg-math-block>([\s\S]*?)</tg-math-block>", block_repl, rich_html, flags=re.IGNORECASE)
    s = re.sub(r"<tg-math>([\s\S]*?)</tg-math>", inline_repl, s, flags=re.IGNORECASE)
    return s


async def send_rich_response(
    bot: Bot,
    chat_id: int,
    raw_markdown: str,
    reply_markup=None,
    status_msg: Optional[Message] = None,
) -> List[Message]:
    """
    Отправляет ответ LLM как нативное Rich Message (Bot API 10.1+).

    Конвейер с каскадом откатов, каждый уровень применяется к СВОЕМУ куску:
      1. sendRichMessage с нативными <tg-math>/<tg-math-block>.
      2. То же, но формулы заменены на Unicode (если Telegram споткнулся о LaTeX).
      3. Обычный sendMessage с ParseMode.HTML, сконвертированный ИЗ ЭТОГО ЖЕ куска.
      4. Тот же кусок как plain text.

    Важно: уровни 3 и 4 конвертируют chunk, а не весь исходный текст, иначе
    при разбиении на несколько сообщений пользователь получил бы дубли.
    """
    if not raw_markdown.strip():
        return []

    # Убираем временное сообщение «Думаю...»
    if status_msg is not None:
        try:
            await status_msg.delete()
        except Exception:
            pass

    logger.info("Ответ ассистента (chat_id=%s, символов=%d)", chat_id, len(raw_markdown))
    rich_html = markdown_to_rich_html(raw_markdown)
    chunks = split_rich_message(rich_html, max_limit=32000)

    sent_messages: List[Message] = []

    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        kb = reply_markup if is_last else None

        # Уровень 1: нативное Rich Message с формулами
        try:
            sent_messages.append(await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(html=chunk),
                reply_markup=kb,
            ))
            continue
        except Exception as e:
            logger.warning("send_rich_message не сработал: %s. Пробуем запасные варианты", e)

        # Уровень 2: те же теги, но формулы в Unicode
        try:
            unicode_chunk = replace_math_tags_with_unicode(chunk)
            sent_messages.append(await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(html=unicode_chunk),
                reply_markup=kb,
            ))
            continue
        except Exception as e:
            logger.warning("Rich Message с Unicode-формулами не сработал: %s", e)

        # Уровень 3: обычный HTML. Конвертируем ИМЕННО этот кусок,
        # вырезая нативные теги формул в текстовый вид.
        html_chunk = _strip_native_tags_to_html(chunk)
        try:
            sent_messages.append(await bot.send_message(
                chat_id=chat_id,
                text=html_chunk,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            ))
            continue
        except Exception as e:
            logger.warning("HTML-отправка не сработала: %s", e)

        # Уровень 4: гарантированный plain text
        plain_text = _strip_all_tags(chunk)
        try:
            sent_messages.append(await bot.send_message(
                chat_id=chat_id,
                text=plain_text,
                parse_mode=None,
                reply_markup=kb,
            ))
        except Exception as e:
            logger.error("Не удалось отправить ответ в чат %s: %s", chat_id, e)

    return sent_messages


def _strip_native_tags_to_html(chunk: str) -> str:
    """Готовит кусок Rich HTML к отправке через обычный parse_mode=HTML.

    Нативные теги форматирования Telegram (h1-h6, ul/li, tg-math, tg-emoji, pre)
    в обычном сообщении не поддерживаются, поэтому переводим их в HTML,
    а формулы — в Unicode через pylatexenc.
    """
    text = re.sub(r"<tg-math-block>([\s\S]*?)</tg-math-block>",
                  lambda m: f"<blockquote><b>{py_html.escape(convert_latex_math(py_html.unescape(m.group(1).strip())), quote=False)}</b></blockquote>",
                  chunk, flags=re.IGNORECASE)
    text = re.sub(r"<tg-math>([\s\S]*?)</tg-math>",
                  lambda m: f"<b>{py_html.escape(convert_latex_math(py_html.unescape(m.group(1).strip())), quote=False)}</b>",
                  text, flags=re.IGNORECASE)
    text = re.sub(r"<h([1-6])>([\s\S]*?)</h\1>", r"<b>\2</b>", text)
    text = re.sub(r"</?(?:ul|ol|li)[^>]*>", lambda m: "\n• " if m.group(0).startswith("<li") else "\n", text)
    text = re.sub(r"<pre><code[^>]*>([\s\S]*?)</code></pre>",
                  lambda m: f"<code>{m.group(1)}</code>", text)
    text = re.sub(r"<tg-emoji[^>]*>([\s\S]*?)</tg-emoji>", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"<table[^>]*>|<t[hd][^>]*>|</t[hd]>|</table>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p>", "", text)
    return text.strip()


def _strip_all_tags(chunk: str) -> str:
    """Убирает вообще всю разметку, оставляя читаемый текст."""
    text = re.sub(r"<t[gh][^>]*>.*?</t[gh]>", " ", chunk, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?[^>]+>", "", text)
    text = py_html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def send_rich_draft_update(
    bot: Bot,
    chat_id: int,
    draft_id: int,
    partial_markdown: str
) -> bool:
    """
    Sends an auto-balanced streaming draft using send_rich_message_draft.
    Returns True on success, False if drafts are not supported or rejected.
    """
    if not partial_markdown.strip():
        return False

    try:
        rich_draft_html = markdown_to_rich_html(partial_markdown, streaming=True)
        return await bot.send_rich_message_draft(
            chat_id=chat_id,
            draft_id=draft_id,
            rich_message=InputRichMessage(html=rich_draft_html)
        )
    except Exception as e:
        logger.debug(f"send_rich_message_draft skipped/failed: {e}")
        return False
