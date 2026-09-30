import html
import logging
import re

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.services.connectors.email_connector import (
    check_inbox,
    is_email_configured,
    send_email,
)
from bot.services.formatters import send_formatted_message
from bot.services.llm import chat_completion

logger = logging.getLogger(__name__)

router = Router(name="email_router")

EMAIL_SUMMARY_PROMPT = """Ты — ассистент по обработке электронной почты.
Составь чёткую сводку входящих писем для Telegram на русском языке:

1. Сколько писем в выборке.
2. По каждому письму:
   - отправитель и дата
   - тема письма (выдели **жирным**)
   - суть в 1–2 предложениях
   - пометка важности: 🔴 если это счёт, чек, код подтверждения, штраф или срочное уведомление
3. Итог: что требуется сделать пользователю и в каком порядке.

Правила:
- Только факты из текста писем, ничего не выдумывай.
- Если письма не относятся к делу (реклама, рассылки) — упомяни их одной строкой.
- Не используй markdown-таблицы.
"""

EMAIL_NOT_CONFIGURED = (
    "✉️ <b>Почта не подключена</b>\n\n"
    "Чтобы бот умел читать письма, сделай три шага:\n"
    "<b>1.</b> В почте (Mail.ru, Яндекс, Gmail) открой "
    "<i>Настройки → Безопасность → Пароли для внешних приложений</i> "
    "и создай отдельный пароль для бота.\n"
    "<b>2.</b> Впиши в файл <code>.env</code>:\n"
    "<code>EMAIL_USER=твой_email@mail.ru</code>\n"
    "<code>EMAIL_PASSWORD=пароль_приложения</code>\n"
    "<b>3.</b> Перезапусти бота."
)


@router.message(Command("mail", "email", "inbox"))
async def cmd_check_mail(message: Message):
    """Показывает сводку последних писем."""
    if not is_email_configured():
        await message.answer(EMAIL_NOT_CONFIGURED, parse_mode=ParseMode.HTML)
        return

    status_msg = await message.answer("✉️ <i>Подключаюсь к почте...</i>")

    try:
        emails = await check_inbox(limit=5, unread_only=False)
    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка чтения почты: %s", exc, exc_info=True)
        await _drop(status_msg, "✉️ Не удалось подключиться к почтовому серверу. Попробуй позже.")
        return

    if not emails:
        await _drop(status_msg, "✉️ <b>В папке «Входящие» писем нет.</b>")
        return

    corpus = "\n\n".join(
        f"--- Письмо #{i} ---\n"
        f"От: {em['sender']}\n"
        f"Дата: {em['date']}\n"
        f"Тема: {em['subject']}\n"
        f"Текст:\n{em['body']}"
        for i, em in enumerate(emails, 1)
    )

    try:
        summary = await chat_completion(
            [
                {"role": "system", "content": EMAIL_SUMMARY_PROMPT},
                {"role": "user", "content": f"Последние письма из почтового ящика:\n\n{corpus}"},
            ],
            temperature=0.3,
            max_tokens=1500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Не удалось сделать сводку писем: %s", exc)
        await _drop(status_msg, "✉️ Не удалось сформировать сводку писем. Попробуй позже.")
        return

    await _drop(status_msg, "")
    await send_formatted_message(
        message,
        f"✉️ <b>Сводка писем ({len(emails)} шт.)</b>\n\n{summary}",
    )


@router.message(Command("sendmail"))
async def cmd_send_mail(message: Message):
    """Отправляет письмо: /sendmail кому@почта | Тема | Текст."""
    if not is_email_configured():
        await message.answer(EMAIL_NOT_CONFIGURED, parse_mode=ParseMode.HTML)
        return

    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2 or "|" not in parts[1]:
        await message.answer(
            "✉️ <b>Как отправить письмо</b>\n\n"
            "<code>/sendmail кому@почта | Тема | Текст письма</code>\n\n"
            "Пример:\n"
            "<code>/sendmail ivan@mail.ru | Смета | Здравствуйте! Направляю расчёт по демонтажу.</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    tokens = [chunk.strip() for chunk in parts[1].split("|")]
    if len(tokens) < 3:
        await message.answer(
            "✉️ Нужны все три части через <code>|</code>: адрес, тема и текст.",
            parse_mode=ParseMode.HTML,
        )
        return

    to_addr, subject, body = tokens[0], tokens[1], tokens[2]

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", to_addr):
        await message.answer(
            f"✉️ Некорректный адрес: <code>{html.escape(to_addr)}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    status_msg = await message.answer(f"✉️ <i>Отправляю на {html.escape(to_addr)}...</i>")

    try:
        await send_email(to_address=to_addr, subject=subject, text_content=body)
    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка отправки письма: %s", exc, exc_info=True)
        await _drop(status_msg, "✉️ Не удалось отправить письмо. Попробуй позже.")
        return

    await _drop(
        status_msg,
        "✉️ <b>Письмо отправлено</b>\n\n"
        f"<b>Кому:</b> <code>{html.escape(to_addr)}</code>\n"
        f"<b>Тема:</b> {html.escape(subject)}\n"
        f"<b>От кого:</b> {html.escape(settings.EMAIL_USER or '')}",
    )


async def _drop(status_msg: Message, text: str) -> None:
    """Убирает статус. Если передан текст — показывает его в том же сообщении."""
    if text:
        try:
            await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        await status_msg.delete()
    except Exception:  # noqa: BLE001
        pass
