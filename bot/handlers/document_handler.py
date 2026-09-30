import logging
import uuid
from io import BytesIO
from pathlib import Path

from aiogram import Bot, F, Router, html
from aiogram.types import Message

from bot.database import crud
from bot.database.db import get_session
from bot.emojis import E_ALERT, E_DOC, E_PHOTO
from bot.services.assistant import stream_assistant_response
from bot.services.file_parser import extract_text_from_file, parse_pdf_smart
from bot.services.formatters import send_formatted_message
from bot.services.vision import analyze_image

logger = logging.getLogger(__name__)

router = Router(name="document_router")

MAX_FILE_MB = 20
HISTORY_LIMIT = 6
TEMP_DIR = Path("temp")


async def _drop_status(status_msg: Message) -> None:
    """Убирает временное сообщение «Читаю...», не падая при ошибке."""
    try:
        await status_msg.delete()
    except Exception:  # noqa: BLE001
        pass


async def _remember(user_id: int, note: str, answer: str) -> None:
    """Сохраняет факт работы с файлом в память диалога."""
    try:
        async with get_session() as session:
            await crud.add_chat_message(session, user_id=user_id, role="user", content=note)
            await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer[:4000])
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не сохранил историю по файлу: %s", exc)


@router.message(F.document)
async def handle_document(message: Message, bot: Bot):
    """Разбирает PDF, Word, Excel, CSV, TXT и картинки-файлы."""
    user_id = message.from_user.id
    doc = message.document
    filename = doc.file_name or "документ"

    if (doc.file_size or 0) / (1024 * 1024) > MAX_FILE_MB:
        await message.answer(
            f"{E_ALERT} Файл больше {MAX_FILE_MB} МБ — Telegram такие не отдаёт боту. "
            f"Пришли сжатый PDF или фото нужной страницы."
        )
        return

    status_msg = await message.answer(f"{E_DOC} <i>Читаю «{html.quote(filename)}»...</i>")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    # Имя файла берём из file_id, а не из file_name: пользователь может прислать
    # путь с '../' или невалидными символами.
    safe_suffix = Path(filename).suffix[:12]
    temp_file = TEMP_DIR / f"doc_{uuid.uuid4().hex[:10]}{safe_suffix}"

    try:
        await bot.download(doc.file_id, destination=str(temp_file))
        mime = (doc.mime_type or "").lower()
        ext = Path(filename).suffix.lower()

        caption = (message.caption or "").strip()

        # 1. Изображение, присланное как документ
        if mime.startswith("image/") or ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic"}:
            answer = await analyze_image(
                image_bytes=temp_file.read_bytes(),
                caption=caption or "Что изображено на фото? Опиши и ответь на вопрос.",
            )
            await _drop_status(status_msg)
            await send_formatted_message(message, answer)
            await _remember(user_id, f"Прислал изображение «{filename}».", answer)
            return

        # 2. PDF: сначала пробуем извлечь текст, при неудаче — рендер в картинку и Vision
        if ext == ".pdf":
            kind, text_content, pdf_image = parse_pdf_smart(str(temp_file))
            if kind == "image" and pdf_image:
                default_prompt = (
                    f"Это скан или визуальный документ «{filename}». "
                    f"Внимательно распознай весь видимый текст, таблицы, суммы, даты и печати, "
                    f"затем дай структурированный разбор на русском."
                )
                answer = await analyze_image(image_bytes=pdf_image, caption=caption or default_prompt)
                await _drop_status(status_msg)
                await send_formatted_message(message, answer)
                await _remember(user_id, f"Прислал визуальный PDF «{filename}».", answer)
                return
            extracted_text = text_content or ""
        else:
            # 3. Word, Excel, CSV, TXT и прочее
            extracted_text = extract_text_from_file(str(temp_file), filename)

        if not extracted_text or extracted_text.startswith(("Не удалось", "Формат файла")):
            await _drop_status(status_msg)
            await message.answer(extracted_text or f"{E_ALERT} Не удалось извлечь текст из файла.")
            return

        async with get_session() as session:
            history = await crud.get_recent_chat_history(session, user_id=user_id, limit=HISTORY_LIMIT)

        if caption:
            query = f"Вопрос пользователя по документу «{filename}»: {caption}\n\nСодержимое:\n{extracted_text}"
        else:
            query = (
                f"Пользователь прислал документ «{filename}» без вопроса. "
                f"Изучи содержимое и дай полезную структурированную сводку: ключевые данные, "
                f"таблицы, суммы, выводы.\n\nСодержимое:\n{extracted_text}"
            )

        answer = await stream_assistant_response(
            message=message,
            user_query=query,
            needs_web=False,
            history=history,
            status_msg=status_msg,
        )
        await _remember(user_id, f"Прислал документ «{filename}»{' с вопросом: ' + caption if caption else ''}.", answer)

    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка обработки документа %s: %s", filename, exc, exc_info=True)
        await _drop_status(status_msg)
        await message.answer(
            f"{E_ALERT} Не удалось обработать «{html.quote(filename)}». "
            f"Попробуй другой файл или пришли фото нужной страницы."
        )
    finally:
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            pass


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot):
    """Анализирует фотографию: детали, чеки, приборы, схемы."""
    user_id = message.from_user.id
    photo = message.photo[-1]  # последний элемент — максимальное разрешение
    status_msg = await message.answer(f"{E_PHOTO} <i>Анализирую изображение...</i>")

    try:
        buf = BytesIO()
        await bot.download(photo.file_id, destination=buf)
        caption = (message.caption or "").strip()

        answer = await analyze_image(
            image_bytes=buf.getvalue(),
            caption=caption or "Что на фото? Распознай текст, детали, маркировку и ответь по существу.",
        )
        await _drop_status(status_msg)
        await send_formatted_message(message, answer)
        await _remember(
            user_id,
            f"Прислал фотографию{' с подписью: ' + caption if caption else ''}.",
            answer,
        )

    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка обработки фото: %s", exc, exc_info=True)
        await _drop_status(status_msg)
        await message.answer(f"{E_ALERT} Не удалось распознать фото. Попробуй ещё раз или опиши вопрос текстом.")
