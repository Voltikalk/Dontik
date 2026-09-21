import io
import os
import uuid
import logging
from pathlib import Path
from aiogram import Router, html, F, Bot
from aiogram.types import Message

from bot.config import settings
from bot.database.db import get_session
from bot.database import crud
from bot.services.file_parser import extract_text_from_file, parse_pdf_smart
from bot.services.vision import analyze_image
from bot.services.assistant import answer_query
from bot.services.formatters import send_formatted_message

logger = logging.getLogger(__name__)

router = Router(name="document_handler_router")


@router.message(F.document)
async def handle_document_message(message: Message, bot: Bot):
    """
    Обработчик прикрепленных файлов и документов (PDF, Word, Excel, CSV, TXT и др.).
    """
    user_id = message.from_user.id

    if settings.ALLOWED_TELEGRAM_IDS and user_id not in settings.ALLOWED_TELEGRAM_IDS:
        await message.answer("⛔ Доступ ограничен. Ваш ID отсутствует в списке доверенных.")
        return

    doc = message.document
    filename = doc.file_name or "документ"
    file_size_mb = (doc.file_size or 0) / (1024 * 1024)

    if file_size_mb > 20:
        await message.answer("⚠️ Размер файла превышает 20 МБ. Telegram Bot API не позволяет скачивать файлы такого размера.")
        return

    status_msg = await message.answer(f"📄 <i>Читаю и анализирую «{html.quote(filename)}»...</i>")

    temp_dir = Path("temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"doc_{uuid.uuid4().hex[:8]}_{filename}"

    try:
        await bot.download(doc.file_id, destination=str(temp_file))

        mime = (doc.mime_type or "").lower()
        ext = Path(filename).suffix.lower()

        # 1. Если документ на самом деле является изображением
        if mime.startswith("image/") or ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
            image_bytes = temp_file.read_bytes()
            async with get_session() as session:
                history = await crud.get_recent_chat_history(session, user_id=user_id, limit=8)

            caption = (message.caption or "").strip()
            answer = await analyze_image(image_bytes=image_bytes, caption=caption, history=history)

            try:
                await status_msg.delete()
            except Exception:
                pass

            await send_formatted_message(message, answer)

            user_log = f"Отправил изображение «{filename}». " + (f"Подпись: «{caption}»" if caption else "Просьба проанализировать.")
            async with get_session() as session:
                await crud.add_chat_message(session, user_id=user_id, role="user", content=user_log)
                await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer)
            return

        # 2. Если документ PDF: проверяем через умный парсер (текст или скан/сертификат)
        if ext == ".pdf":
            kind, text_content, pdf_image_bytes = parse_pdf_smart(str(temp_file))
            if kind == "image" and pdf_image_bytes:
                async with get_session() as session:
                    history = await crud.get_recent_chat_history(session, user_id=user_id, limit=8)

                caption = (message.caption or "").strip()
                pdf_caption = caption if caption else (
                    f"Это визуальный PDF документ или сертификат «{filename}». "
                    "Внимательно изучи его, распознай весь видимый текст, имена, названия, сертификаты, даты, печати или таблицы "
                    "и подготовь подробный структурированный ответ на русском языке."
                )
                answer = await analyze_image(image_bytes=pdf_image_bytes, caption=pdf_caption, history=history)

                try:
                    await status_msg.delete()
                except Exception:
                    pass

                await send_formatted_message(message, answer)

                user_log = f"Отправил визуальный PDF документ «{filename}». " + (f"Подпись: «{caption}»" if caption else "Просьба разобрать содержимое.")
                async with get_session() as session:
                    await crud.add_chat_message(session, user_id=user_id, role="user", content=user_log)
                    await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer)
                return
            else:
                extracted_text = text_content or ""
        else:
            # 3. Извлечение текста из других документов (Word, Excel, CSV, TXT)
            extracted_text = extract_text_from_file(str(temp_file), filename)

        if not extracted_text or extracted_text.startswith("Не удалось") or extracted_text.startswith("Формат файла"):
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.answer(extracted_text)
            return

        async with get_session() as session:
            history = await crud.get_recent_chat_history(session, user_id=user_id, limit=3)

        caption = (message.caption or "").strip()
        if caption:
            query = f"{caption}\n\n[Прикрепленный документ: «{filename}»]\n{extracted_text}"
        else:
            query = (
                f"Пользователь прислал документ «{filename}».\n"
                f"Внимательно изучи его содержимое, подготовь структурированное резюме, "
                f"выдели ключевые пункты, данные таблиц, выводы или важные показатели:\n\n{extracted_text}"
            )

        answer = await answer_query(user_query=query, needs_web=False, history=history)

        try:
            await status_msg.delete()
        except Exception:
            pass

        await send_formatted_message(message, answer)

        user_log = f"Отправил документ «{filename}». " + (f"Запрос: «{caption}»" if caption else "Просьба разобрать содержимое.")
        async with get_session() as session:
            await crud.add_chat_message(session, user_id=user_id, role="user", content=user_log)
            await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer)

    except Exception as e:
        logger.error(f"Ошибка при обработке документа {filename}: {e}", exc_info=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(f"⚠️ Не удалось обработать файл «{html.quote(filename)}»: {e}")
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass


@router.message(F.photo)
async def handle_photo_message(message: Message, bot: Bot):
    """
    Обработчик входящих фотографий (автозапчасти, чеки, приборы, схемы, документы).
    """
    user_id = message.from_user.id

    if settings.ALLOWED_TELEGRAM_IDS and user_id not in settings.ALLOWED_TELEGRAM_IDS:
        await message.answer("⛔ Доступ ограничен. Ваш ID отсутствует в списке доверенных.")
        return

    # Берем фото в наилучшем доступном разрешении (последний элемент в массиве)
    photo = message.photo[-1]
    status_msg = await message.answer("🖼 <i>Анализирую изображение...</i>")

    try:
        buf = io.BytesIO()
        await bot.download(photo.file_id, destination=buf)
        image_bytes = buf.getvalue()

        async with get_session() as session:
            history = await crud.get_recent_chat_history(session, user_id=user_id, limit=8)

        caption = (message.caption or "").strip()
        answer = await analyze_image(image_bytes=image_bytes, caption=caption, history=history)

        try:
            await status_msg.delete()
        except Exception:
            pass

        await send_formatted_message(message, answer)

        user_log = "Отправил фотографию. " + (f"Подпись: «{caption}»" if caption else "Просьба распознать.")
        async with get_session() as session:
            await crud.add_chat_message(session, user_id=user_id, role="user", content=user_log)
            await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer)

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(f"⚠️ Не удалось распознать фотографию: {e}")
