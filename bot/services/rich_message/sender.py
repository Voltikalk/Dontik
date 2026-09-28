import re
import html as py_html
import logging
from typing import Optional, List
from aiogram import Bot
from aiogram.types import Message, InputRichMessage
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from bot.services.formatters import convert_latex_math, md_to_telegram_html
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
    Sends an LLM answer as a native Telegram Rich Message (Bot API 10.1+):
    - Converts Markdown and LaTeX into Rich HTML with native <tg-math-block> and <tg-math>.
    - Sends the entire answer in ONE single message (no reply_to_message_id, no split messages).
    - Cleans up any temporary status_msg.
    - Robust fallback:
        1. If sendRichMessage fails due to invalid LaTeX, replaces formulas with Unicode and retries.
        2. If still failing, falls back to standard sendMessage with ParseMode.HTML.
        3. If HTML parsing fails, sends plain text.
    - All Telegram error responses are logged.
    """
    if not raw_markdown.strip():
        return []

    # Clean up temporary "thinking" status message
    if status_msg is not None:
        try:
            await status_msg.delete()
        except Exception:
            pass

    rich_html = markdown_to_rich_html(raw_markdown)
    chunks = split_rich_message(rich_html, max_limit=32000)

    sent_messages: List[Message] = []

    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        kb = reply_markup if is_last else None

        # Attempt 1: Native send_rich_message with LaTeX tags
        try:
            msg = await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(html=chunk),
                reply_markup=kb
            )
            sent_messages.append(msg)
            continue
        except Exception as e:
            logger.warning(
                f"send_rich_message error from Telegram API: {e}. Starting fallback pipeline...",
                exc_info=True
            )

        # Attempt 2: Fallback replacing <tg-math-block> with Unicode blockquotes
        try:
            unicode_chunk = replace_math_tags_with_unicode(chunk)
            msg = await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(html=unicode_chunk),
                reply_markup=kb
            )
            sent_messages.append(msg)
            continue
        except Exception as e2:
            logger.warning(
                f"send_rich_message with Unicode fallback failed: {e2}. Falling back to standard sendMessage...",
                exc_info=True
            )

        # Attempt 3: Fallback to standard sendMessage with ParseMode.HTML
        try:
            std_html = md_to_telegram_html(raw_markdown)
            msg = await bot.send_message(
                chat_id=chat_id,
                text=std_html,
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            sent_messages.append(msg)
            continue
        except Exception as e3:
            logger.warning(
                f"Standard sendMessage HTML failed: {e3}. Sending plain text...",
                exc_info=True
            )

        # Attempt 4: Safe plain text fallback
        plain_text = re.sub(r'</?[^>]+>', '', chunk)
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=plain_text,
                parse_mode=None,
                reply_markup=kb
            )
            sent_messages.append(msg)
        except Exception as e4:
            logger.error(f"Critical failure sending message to chat {chat_id}: {e4}", exc_info=True)

    return sent_messages


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
