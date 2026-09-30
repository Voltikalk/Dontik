"""
Единая точка обработки пользовательского ввода: голос, аудио и текст.

Раньше логика распознавания намерений была продублирована в voice_handler.py и
general_handler.py, из-за чего они разошлись по поведению. Здесь один путь:
скачивание -> транскрибация -> разбор интента -> действие.
"""

import logging
import uuid
from pathlib import Path
from typing import Optional

from aiogram import F, Router, Bot, html
from aiogram.enums import ChatAction, ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from bot.database import crud
from bot.database.db import get_session
from bot.emojis import E_ALERT, E_CHECK, E_MIC, E_MUTE, E_QUESTION, E_SEARCH, E_THINK
from bot.handlers.states import EditEntryState, FindItemState, GarageEntryState
from bot.keyboards.inline import get_entry_confirm_keyboard, get_tasks_keyboard
from bot.services import draft_store
from bot.services.assistant import stream_assistant_response
from bot.services.dates import resolve_due
from bot.services.formatters import (
    format_found_items,
    format_fuel_card,
    format_item_card,
    format_search_prompt,
    format_service_card,
    format_task_card,
    format_tasks_list,
)
from bot.services.intent_parser import parse_user_intent
from bot.services.speech_to_text import transcribe_voice

logger = logging.getLogger(__name__)

router = Router(name="input_router")

TEMP_DIR = Path("temp")
HISTORY_LIMIT = 12
HISTORY_CHARS_PER_MSG = 400

# Поля, которые LLM отдаёт числами — приводим перед сохранением в БД.
_INT_FIELDS = ("liters", "cost", "odometer")


async def _typing(bot: Bot, chat_id: int) -> None:
    """Показывает «печатает...», чтобы ожидание не выглядело зависанием."""
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception:  # noqa: BLE001 - индикатор не критичен
        pass


def _coerce_numbers(data: dict) -> dict:
    """Приводит строковые числа от LLM к float/int, иначе БД упадёт на записи."""
    for field in _INT_FIELDS:
        value = data.get(field)
        if value is None or isinstance(value, (int, float)):
            continue
        cleaned = str(value).replace(" ", "").replace(",", ".").replace("₽", "").strip()
        try:
            number = float(cleaned)
        except ValueError:
            data[field] = None
            continue
        data[field] = int(number) if field == "odometer" else number
    return data


async def _load_history(user_id: int) -> list[dict]:
    async with get_session() as session:
        return await crud.get_recent_chat_history(session, user_id=user_id, limit=HISTORY_LIMIT)


def _history_as_context(history: list[dict]) -> Optional[str]:
    """Собирает компактный контекст последних реплик для разрешения местоимений."""
    if not history:
        return None
    recent = history[-6:]
    lines = [
        f"{'Пользователь' if item['role'] == 'user' else 'Ассистент'}: {item['content'][:HISTORY_CHARS_PER_MSG]}"
        for item in recent
    ]
    return "\n".join(lines) if lines else None


async def _remember(user_id: int, user_text: str, answer: str) -> None:
    """Сохраняет реплику и ответ в память диалога. Ошибки не критичны."""
    try:
        async with get_session() as session:
            await crud.add_chat_message(session, user_id=user_id, role="user", content=user_text)
            await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось сохранить историю диалога: %s", exc)


# --- Точки входа ---

@router.message(F.voice | F.audio | F.video_note)
async def handle_voice(message: Message, bot: Bot, state: FSMContext):
    """Голосовое сообщение, голосовая заметка или видеокружок -> транскрибация."""
    media: Optional[TelegramObject] = message.voice or message.audio or message.video_note
    if not media:
        return

    await _typing(bot, message.chat.id)
    await state.clear()

    status_msg = await message.answer(f"{E_MIC} <i>Слушаю...</i>")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".mp4" if message.video_note else ".ogg"
    temp_file = str(TEMP_DIR / f"voice_{uuid.uuid4().hex[:8]}{suffix}")

    try:
        await bot.download(file=media.file_id, destination=temp_file)
    except Exception as exc:  # noqa: BLE001
        logger.error("Не удалось скачать аудио: %s", exc)
        await _replace_status(status_msg, f"{E_ALERT} Не удалось получить аудиофайл. Попробуй ещё раз.")
        return

    try:
        transcript = await transcribe_voice(file_path=temp_file)
    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка транскрибации: %s", exc)
        await _replace_status(status_msg, f"{E_ALERT} Не удалось распознать речь. Попробуй записать ещё раз.")
        return
    finally:
        try:
            Path(temp_file).unlink(missing_ok=True)
        except OSError:
            pass

    if not transcript or not transcript.strip():
        await _replace_status(status_msg, f"{E_MUTE} Не разобрал слова. Скажи чётче или чуть громче.")
        return

    logger.info("Транскрипция: %s", transcript)
    await _replace_status(status_msg, f"{E_MIC} <i>Разбираю...</i>")
    await process_input(message, message.bot, state, transcript, is_voice=True)


async def _replace_status(status_msg: Message, text: str) -> None:
    """Пытается отредактировать статус, при неудаче отправляет новым сообщением."""
    try:
        await status_msg.edit_text(text)
    except Exception:  # noqa: BLE001
        try:
            await status_msg.edit_text(text, parse_mode=ParseMode.NONE)
        except Exception:
            pass


# --- Ядро: разбор интента и выполнение действия ---

async def process_input(
    message: Message,
    bot: Bot,
    state: FSMContext,
    text: str,
    is_voice: bool = False,
) -> None:
    """Разбирает намерение и выполняет соответствующее действие."""
    user_id = message.from_user.id
    text = text.strip()
    if not text:
        return

    await _typing(bot, message.chat.id)

    history = await _load_history(user_id)
    parsed = await parse_user_intent(text, context=_history_as_context(history))
    intent = parsed.get("intent", "unknown")
    data = _coerce_numbers(parsed.get("data") or {})

    logger.info("Интент=%s голос=%s", intent, is_voice)

    if intent == "item_find":
        await _do_item_find(message, user_id, data.get("search_query") or text)
        return

    if intent == "task_list":
        await send_tasks_list(message, user_id)
        return

    if intent == "task_delete":
        await _do_task_delete(message, user_id, data.get("title") or text)
        return

    if intent in ("fuel", "service", "item_save", "task_save"):
        await _show_confirm_card(message, state, user_id, intent, data, text if is_voice else "")
        return

    # Всё остальное — общий вопрос ассистенту (включая математику).
    await _do_assistant(message, bot, user_id, data, text, history)


async def _show_confirm_card(
    message: Message,
    state: FSMContext,
    user_id: int,
    intent: str,
    data: dict,
    transcript: str,
) -> None:
    """Показывает карточку с распознанными данными и кнопками."""
    draft_id = draft_store.save_draft(user_id=user_id, intent=intent, data=data)

    await state.set_state(GarageEntryState.waiting_confirmation)
    await state.update_data(draft_id=draft_id, intent=intent, transcript=transcript)

    card = _render_card(intent, data, transcript)
    await message.answer(
        card,
        reply_markup=get_entry_confirm_keyboard(draft_id),
        parse_mode=ParseMode.HTML,
    )


def _render_card(intent: str, data: dict, transcript: str = "") -> str:
    """Собирает текст карточки для нужного типа записи."""
    if intent == "fuel":
        return format_fuel_card(data, transcript)
    if intent == "service":
        return format_service_card(data, transcript)
    if intent == "item_save":
        return format_item_card(data, transcript)
    if intent == "task_save":
        return format_task_card(data, transcript)
    return "Не удалось разобрать данные."


async def _do_item_find(message: Message, user_id: int, query: str) -> None:
    query = (query or "").strip()
    async with get_session() as session:
        found = await crud.search_item_locations(session, user_id=user_id, query=query)

    await message.answer(format_found_items(found, query))


async def _do_task_delete(message: Message, user_id: int, query: str) -> None:
    """Удаляет задачи, чей заголовок содержит запрос."""
    needle = (query or "").strip().lower()
    async with get_session() as session:
        tasks = await crud.get_active_tasks(session, user_id=user_id, limit=200)

    matches = [t for t in tasks if needle and needle in (t.title or "").lower()]

    if not matches:
        await message.answer(
            f"{E_QUESTION} Не нашёл задач, подходящих под «{html.quote(needle)}».\n"
            f"Посмотри текущий список командой /tasks."
        )
        return

    if len(matches) == 1:
        task = matches[0]
        async with get_session() as session:
            removed = await crud.delete_task(session, user_id=user_id, task_id=task.id)
        if removed:
            await message.answer(f"{E_CHECK} Задача «<b>{html.quote(task.title)}</b>» удалена.")
        else:
            await message.answer(f"{E_ALERT} Не удалось удалить задачу.")
        return

    await message.answer(
        f"{E_QUESTION} Под запрос «<b>{html.quote(needle)}</b>» подходит несколько задач. "
        f"Уточни, какую удалить:\n"
        + "\n".join(f"• {html.quote(t.title)}" for t in matches[:10])
    )


async def _do_assistant(
    message: Message,
    bot: Bot,
    user_id: int,
    data: dict,
    raw_text: str,
    history: list[dict],
) -> None:
    """Отвечает на общий вопрос: с веб-поиском или без, потоково."""
    needs_web = bool(data.get("needs_web_search"))
    query = data.get("user_query") or raw_text
    search_query = data.get("search_query")

    wait_text = (
        f"{E_SEARCH} <i>Ищу в интернете...</i>"
        if needs_web
        else f"{E_THINK} <i>Думаю...</i>"
    )
    status_msg = await message.answer(wait_text)

    try:
        answer = await stream_assistant_response(
            message=message,
            user_query=query,
            needs_web=needs_web,
            search_query=search_query,
            history=history,
            status_msg=status_msg,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка ассистента: %s", exc, exc_info=True)
        await _replace_status(
            status_msg,
            f"{E_ALERT} Не удалось получить ответ. Попробуй переформулировать или повторить чуть позже.",
        )
        return

    await _remember(user_id, query, answer)


async def send_tasks_list(target, user_id: int, edit: bool = False) -> None:
    """Показывает список задач. target — Message, по которому отвечаем или редактируем."""
    async with get_session() as session:
        tasks = await crud.get_active_tasks(session, user_id=user_id)

    text = format_tasks_list(tasks)
    kb = get_tasks_keyboard(tasks)

    if edit:
        try:
            await target.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
            return
        except Exception:  # noqa: BLE001
            pass
    await target.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# --- Ввод в режиме правки карточки и режиме поиска вещи ---

@router.message(EditEntryState.waiting_field, F.text)
async def handle_edit_field(message: Message, state: FSMContext):
    """Принимает исправленное значение поля карточки."""
    message.from_user.id
    data = await state.get_data()
    draft_id = data.get("draft_id", "")
    field = data.get("editing_field", "")
    value = (message.text or "").strip()

    if not value:
        await message.answer("Пришли новое значение текстом — я обновлю карточку.")
        return

    draft = draft_store.get_draft(draft_id)
    if not draft:
        await state.clear()
        await message.answer(f"{E_ALERT} Карточка уже неактуальна. Скажи это ещё раз — сделаю новую.")
        return

    if field in ("liters", "cost", "odometer"):
        cleaned = value.replace(" ", "").replace(",", ".").replace("₽", "")
        try:
            number = float(cleaned)
        except ValueError:
            await message.answer(f"{E_ALERT} «{html.quote(value)}» — это не число. Пришли только число.")
            return
        value = int(number) if field == "odometer" else number
    elif field == "due_date":
        parsed_due = resolve_due(value, value)
        if parsed_due:
            value = parsed_due.strftime("%Y-%m-%dT%H:%M:%S")

    draft_store.update_draft(draft_id, {field: value})
    if field == "due_date":
        draft_store.update_draft(draft_id, {"due_at": resolve_due(value, value)})

    intent = draft.get("intent", "")
    card = _render_card(intent, draft.get("data", {}), draft.get("data", {}).get("transcript", ""))

    await message.answer(
        f"{E_CHECK} Поправил: <b>{html.quote(field)}</b> = <code>{html.quote(str(value))}</code>",
        parse_mode=ParseMode.HTML,
    )
    await message.answer(
        card,
        reply_markup=get_entry_confirm_keyboard(draft_id),
        parse_mode=ParseMode.HTML,
    )
    await state.update_data(editing_field="")


@router.message(FindItemState.waiting_query, F.text)
async def handle_find_query(message: Message, state: FSMContext):
    """Ищет вещь по запросу, введённому после нажатия кнопки «Поиск вещи»."""
    query = (message.text or "").strip()
    await state.clear()

    if not query:
        await message.answer(format_search_prompt())
        return

    await _do_item_find(message, message.from_user.id, query)