import re
import html as py_html
import asyncio
import hashlib
import logging
from typing import List, Optional
from aiogram import Bot
from aiogram.types import Message, BufferedInputFile, LinkPreviewOptions
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from bot.services.message_splitter import Segment
from .renderer import render_latex_to_png, RenderedFormula

logger = logging.getLogger(__name__)


async def send_rendered_segments(
    bot: Bot,
    chat_id: int,
    segments: List[Segment],
    reply_to_message_id: Optional[int] = None,
    reply_markup=None,
    status_msg: Optional[Message] = None,
    message_delay: float = 0.2
) -> List[Message]:
    """
    Sends an ordered sequence of 'text' and 'formula' segments to Telegram:
    - 'text': sendMessage with parse_mode=HTML (escaped, headings in bold).
    - 'formula': rendered to PNG and sent as sendPhoto without caption.
                 If aspect ratio is extreme (>4.5:1), sent as sendDocument.
    - Fallback: If LaTeX rendering fails or times out, sends source in <pre><code>.
    - Rate limit: Short pause between messages and handles TelegramRetryAfter.
    - Status message: If the first segment is text, edits status_msg in place for a smooth transition.
                      Otherwise, safely removes status_msg.
    """
    if not segments:
        return []

    sent_messages: List[Message] = []
    total_segments = len(segments)

    for i, seg in enumerate(segments):
        is_first = (i == 0)
        is_last = (i == total_segments - 1)
        kb = reply_markup if is_last else None

        if i > 0:
            await asyncio.sleep(message_delay)

        if seg.type == "text":
            text_content = seg.content.strip()
            if not text_content:
                continue

            # First text segment can edit status_msg smoothly in place
            if is_first and status_msg is not None:
                edited = False
                try:
                    await status_msg.edit_text(
                        text_content,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb,
                        link_preview_options=LinkPreviewOptions(is_disabled=True)
                    )
                    sent_messages.append(status_msg)
                    edited = True
                except TelegramBadRequest as e:
                    logger.warning(f"Error editing status_msg with HTML: {e}. Trying plain text fallback...")
                    try:
                        plain_txt = re.sub(r'</?[^>]+>', '', text_content)
                        await status_msg.edit_text(
                            plain_txt,
                            parse_mode=None,
                            reply_markup=kb,
                            link_preview_options=LinkPreviewOptions(is_disabled=True)
                        )
                        sent_messages.append(status_msg)
                        edited = True
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"Failed to edit status_msg: {e}")

                if edited:
                    continue
                else:
                    # If editing failed, delete status_msg and send anew
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                    status_msg = None

            # Normal send message with retry_after handling
            while True:
                try:
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=text_content,
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=reply_to_message_id,
                        reply_markup=kb,
                        link_preview_options=LinkPreviewOptions(is_disabled=True)
                    )
                    sent_messages.append(msg)
                    break
                except TelegramRetryAfter as e:
                    logger.warning(f"Hit Telegram rate limit (retry_after={e.retry_after}s). Sleeping...")
                    await asyncio.sleep(e.retry_after + 0.5)
                except TelegramBadRequest as e:
                    logger.warning(f"Telegram parse_mode=HTML failed ({e}), sending plain text...")
                    plain_txt = re.sub(r'</?[^>]+>', '', text_content)
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=plain_txt,
                        parse_mode=None,
                        reply_to_message_id=reply_to_message_id,
                        reply_markup=kb,
                        link_preview_options=LinkPreviewOptions(is_disabled=True)
                    )
                    sent_messages.append(msg)
                    break
                except Exception as e:
                    logger.error(f"Failed to send text segment: {e}", exc_info=True)
                    break

        elif seg.type == "formula":
            formula_latex = seg.content.strip()
            if not formula_latex:
                continue

            # If the response starts with a formula, remove the status message first
            if is_first and status_msg is not None:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                status_msg = None

            # Render formula to PNG
            rendered: Optional[RenderedFormula] = None
            try:
                rendered = await render_latex_to_png(formula_latex, timeout=6.0)
            except Exception as e:
                logger.error(
                    f"Formula render error for '{formula_latex[:60]}': {e}. Using fallback <pre>.",
                    exc_info=True
                )
                rendered = None

            formula_hash = hashlib.md5(formula_latex.encode("utf-8")).hexdigest()[:8]

            while True:
                try:
                    if rendered is None:
                        # Fallback: send LaTeX source inside <pre><code>
                        esc_latex = py_html.escape(formula_latex, quote=False)
                        fallback_html = f"<pre><code>{esc_latex}</code></pre>"
                        msg = await bot.send_message(
                            chat_id=chat_id,
                            text=fallback_html,
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=reply_to_message_id,
                            reply_markup=kb
                        )
                        sent_messages.append(msg)
                        break
                    else:
                        photo_file = BufferedInputFile(
                            rendered.png_bytes,
                            filename=f"formula_{formula_hash}.png"
                        )
                        if rendered.is_extreme_aspect_ratio:
                            # Send as document to avoid compression/cropping of extreme aspect ratios
                            msg = await bot.send_document(
                                chat_id=chat_id,
                                document=photo_file,
                                reply_to_message_id=reply_to_message_id,
                                reply_markup=kb
                            )
                        else:
                            # Send as photo without caption
                            msg = await bot.send_photo(
                                chat_id=chat_id,
                                photo=photo_file,
                                reply_to_message_id=reply_to_message_id,
                                reply_markup=kb
                            )
                        sent_messages.append(msg)
                        break
                except TelegramRetryAfter as e:
                    logger.warning(f"Hit Telegram rate limit (retry_after={e.retry_after}s). Sleeping...")
                    await asyncio.sleep(e.retry_after + 0.5)
                except Exception as e:
                    logger.error(f"Failed to send formula image: {e}. Attempting text fallback...", exc_info=True)
                    try:
                        esc_latex = py_html.escape(formula_latex, quote=False)
                        msg = await bot.send_message(
                            chat_id=chat_id,
                            text=f"<pre><code>{esc_latex}</code></pre>",
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=reply_to_message_id,
                            reply_markup=kb
                        )
                        sent_messages.append(msg)
                    except Exception:
                        pass
                    break

    # If status_msg was not handled (e.g. error before first message), clean it up
    if status_msg is not None and status_msg not in sent_messages:
        try:
            await status_msg.delete()
        except Exception:
            pass

    return sent_messages
