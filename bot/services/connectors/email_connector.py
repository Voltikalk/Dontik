import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple

from bot.config import settings

logger = logging.getLogger(__name__)


def resolve_email_hosts(email_address: str) -> Tuple[str, int, str, int]:
    """
    Автоматически определяет IMAP и SMTP хосты по домену почты, если они не заданы в .env.
    """
    domain = email_address.lower().split("@")[-1] if "@" in email_address else ""

    imap_host = settings.EMAIL_IMAP_HOST
    imap_port = settings.EMAIL_IMAP_PORT or 993
    smtp_host = settings.EMAIL_SMTP_HOST
    smtp_port = settings.EMAIL_SMTP_PORT or 465

    if not imap_host or not smtp_host:
        if domain in ["mail.ru", "inbox.ru", "bk.ru", "list.ru"]:
            imap_host = imap_host or "imap.mail.ru"
            smtp_host = smtp_host or "smtp.mail.ru"
        elif domain in ["yandex.ru", "ya.ru"]:
            imap_host = imap_host or "imap.yandex.ru"
            smtp_host = smtp_host or "smtp.yandex.ru"
        elif domain in ["gmail.com"]:
            imap_host = imap_host or "imap.gmail.com"
            smtp_host = smtp_host or "smtp.gmail.com"
        elif domain in ["rambler.ru"]:
            imap_host = imap_host or "imap.rambler.ru"
            smtp_host = smtp_host or "smtp.rambler.ru"
        else:
            imap_host = imap_host or f"imap.{domain}"
            smtp_host = smtp_host or f"smtp.{domain}"

    return imap_host, imap_port, smtp_host, smtp_port


def is_email_configured() -> bool:
    """Проверяет, заданы ли логин и пароль почты в настройках."""
    return bool(settings.EMAIL_USER and settings.EMAIL_PASSWORD and "your_" not in settings.EMAIL_USER)


def _clean_header(header_val: Any) -> str:
    """Декодирует заголовки писем (тему, отправителя) с учетом кодировок."""
    if not header_val:
        return ""
    decoded_parts = decode_header(header_val)
    result = []
    for part, enc in decoded_parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(enc or "utf-8", errors="replace"))
            except Exception:
                result.append(part.decode("cp1251", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _fetch_emails_sync(limit: int = 5, unread_only: bool = True) -> List[Dict[str, Any]]:
    """Синхронное подключение и чтение писем по IMAP."""
    user = settings.EMAIL_USER
    pwd = settings.EMAIL_PASSWORD
    if not user or not pwd:
        return []

    imap_host, imap_port, _, _ = resolve_email_hosts(user)
    logger.info(f"Подключение к IMAP {imap_host}:{imap_port} под {user}...")

    mail = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=15)
    mail.login(user, pwd)
    mail.select("INBOX")

    search_criteria = "UNSEEN" if unread_only else "ALL"
    status, messages = mail.search(None, search_criteria)
    if status != "OK" or not messages[0]:
        # Если непрочитанных нет, пробуем получить последние любые
        if unread_only:
            status, messages = mail.search(None, "ALL")
            if status != "OK" or not messages[0]:
                mail.logout()
                return []
        else:
            mail.logout()
            return []

    mail_ids = messages[0].split()
    # Берем последние limit писем
    latest_ids = mail_ids[-limit:]
    latest_ids.reverse()

    emails_list = []

    for m_id in latest_ids:
        status, data = mail.fetch(m_id, "(RFC822)")
        if status != "OK" or not data or not data[0]:
            continue

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = _clean_header(msg.get("Subject", "Без темы"))
        sender = _clean_header(msg.get("From", "Неизвестный отправитель"))
        date = msg.get("Date", "")

        # Извлечение текста тела письма
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disp = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disp:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body = payload.decode(charset, errors="replace")
                        except Exception:
                            body = payload.decode("cp1251", errors="replace")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    body = payload.decode(charset, errors="replace")
                except Exception:
                    body = payload.decode("cp1251", errors="replace")

        # Ограничиваем тело письма для безопасности контекста
        clean_body = (body or "").strip()
        if len(clean_body) > 1000:
            clean_body = clean_body[:1000] + "..."

        emails_list.append({
            "id": m_id.decode() if isinstance(m_id, bytes) else str(m_id),
            "sender": sender,
            "subject": subject,
            "date": date,
            "body": clean_body
        })

    mail.logout()
    return emails_list


def _send_email_sync(to_address: str, subject: str, text_content: str) -> bool:
    """Синхронная отправка письма по SMTP."""
    user = settings.EMAIL_USER
    pwd = settings.EMAIL_PASSWORD
    if not user or not pwd:
        raise ValueError("Почта не настроена в переменных окружения.")

    _, _, smtp_host, smtp_port = resolve_email_hosts(user)
    logger.info(f"Отправка письма через SMTP {smtp_host}:{smtp_port} на {to_address}...")

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(text_content, "plain", "utf-8"))

    if smtp_port == 465:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
        server.starttls()

    server.login(user, pwd)
    server.sendmail(user, [to_address], msg.as_string())
    server.quit()
    return True


async def check_inbox(limit: int = 5, unread_only: bool = True) -> List[Dict[str, Any]]:
    """Асинхронная обертка для проверки почты."""
    return await asyncio.to_thread(_fetch_emails_sync, limit, unread_only)


async def send_email(to_address: str, subject: str, text_content: str) -> bool:
    """Асинхронная обертка для отправки письма."""
    return await asyncio.to_thread(_send_email_sync, to_address, subject, text_content)
