import re
import html
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from openai import AsyncOpenAI

from bot.config import settings
from bot.services.connectors.email_connector import (
    check_inbox,
    send_email,
    is_email_configured
)
from bot.services.formatters import send_formatted_message
from bot.database.db import get_session
from bot.database import crud

logger = logging.getLogger(__name__)

router = Router(name="email_handler_router")

EMAIL_SUMMARY_PROMPT = """Ты — интеллектуальный ассистент по обработке электронной почты.
Твоя задача — составить четкую сводку входящих писем для Telegram:
1. Количество полученных писем.
2. По каждому письму:
   - Отправитель и дата
   - Тема письма (выдели **жирным**)
   - Краткая суть в 1-2 предложениях
   - Важность/срочность (если это счет, чек, код подтверждения, важное уведомление — поставь пометку 🔴 Важно или 🧾 Чек)
3. Общий вывод (требуется ли срочное действие от пользователя).

Отвечай вежливо, структурированно и лаконично на русском языке.
"""


@router.message(Command("mail", "email", "inbox"))
async def cmd_check_mail(message: Message):
    """
    Обработчик команды /mail для проверки входящих писем.
    """
    user_id = message.from_user.id

    if not is_email_configured():
        help_text = (
            "✉️ <b>Коннектор электронной почты</b>\n\n"
            "Почтовый ящик еще не подключен в файле конфигурации <code>.env</code>.\n\n"
            "<b>Как подключить за 1 минуту:</b>\n"
            "1. В почте (Mail.ru, Яндекс, Gmail) зайдите в Настройки → Безопасность → <b>Пароли для внешних приложений</b> (App Passwords) и создайте отдельный пароль для бота.\n"
            "2. В файле <code>.env</code> укажите:\n"
            "<code>EMAIL_USER=vash_email@mail.ru</code>\n"
            "<code>EMAIL_PASSWORD=vash_parol_prilozheniya</code>\n\n"
            "<i>После этого бот сможет читать входящие, искать важные письма и отправлять сообщения по вашей команде!</i>"
        )
        await message.answer(help_text)
        return

    status_msg = await message.answer("📬 <i>Подключаюсь к почтовому серверу и проверяю входящие...</i>")

    try:
        emails = await check_inbox(limit=5, unread_only=False)

        if not emails:
            await status_msg.edit_text("📭 <b>В папке «Входящие» писем не найдено.</b>")
            return

        # Формируем текст для саммари через LLM
        email_items_text = []
        for idx, em in enumerate(emails, 1):
            email_items_text.append(
                f"--- Письмо #{idx} ---\n"
                f"От: {em['sender']}\n"
                f"Дата: {em['date']}\n"
                f"Тема: {em['subject']}\n"
                f"Текст:\n{em['body']}\n"
            )

        client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY,
            max_retries=0
        )
        resp = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": EMAIL_SUMMARY_PROMPT},
                {"role": "user", "content": f"Вот последние письма из почтового ящика:\n\n{full_raw_text}\n\nСделай структурированную сводку."}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        summary = resp.choices[0].message.content or "Не удалось сформировать сводку писем."

        try:
            await status_msg.delete()
        except Exception:
            pass

        final_answer = f"📬 <b>Сводка последних писем ({len(emails)} шт.):</b>\n\n{summary}"
        await send_formatted_message(message, final_answer)

        # Сохраняем в память диалога
        async with get_session() as session:
            await crud.add_chat_message(session, user_id=user_id, role="user", content="Проверил почту через /mail")
            await crud.add_chat_message(session, user_id=user_id, role="assistant", content=final_answer)

    except Exception as e:
        logger.error(f"Ошибка при проверке почты: {e}", exc_info=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(f"⚠️ Ошибка при подключении к почтовому серверу: {e}")


@router.message(Command("sendmail"))
async def cmd_send_mail(message: Message):
    """
    Обработчик команды /sendmail для отправки письма.
    Формат: /sendmail to@example.com | Тема | Текст
    """
    if not is_email_configured():
        await message.answer("⚠️ Почта не настроена в <code>.env</code> (нужны <code>EMAIL_USER</code> и <code>EMAIL_PASSWORD</code>).")
        return

    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2 or "|" not in parts[1]:
        help_text = (
            "✉️ <b>Как отправить письмо через бота:</b>\n\n"
            "Используйте формат через вертикальную черту <code>|</code>:\n"
            "<code>/sendmail poluchatel@mail.ru | Тема письма | Текст вашего сообщения</code>\n\n"
            "<b>Пример:</b>\n"
            "<code>/sendmail ivan@mail.ru | Смета на скважины | Привет, направляю предварительный расчет по демонтажу.</code>"
        )
        await message.answer(help_text)
        return

    payload = parts[1]
    tokens = [t.strip() for t in payload.split("|")]

    if len(tokens) < 3:
        await message.answer("⚠️ Укажите все три части через <code>|</code>: адрес получателя, тему и текст.")
        return

    to_addr, subject, body = tokens[0], tokens[1], tokens[2]

    # Базовая валидация email
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", to_addr):
        await message.answer(f"⚠️ Некорректный email адрес получателя: <code>{html.quote(to_addr)}</code>")
        return

    status_msg = await message.answer(f"📤 <i>Отправляю письмо на {html.quote(to_addr)}...</i>")

    try:
        await send_email(to_address=to_addr, subject=subject, text_content=body)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(
            f"✅ <b>Письмо успешно отправлено!</b>\n\n"
            f"<b>Кому:</b> <code>{html.quote(to_addr)}</code>\n"
            f"<b>Тема:</b> {html.quote(subject)}\n"
            f"<b>Отправитель:</b> {html.quote(settings.EMAIL_USER or '')}"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке письма: {e}", exc_info=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(f"⚠️ Не удалось отправить письмо: {e}")
