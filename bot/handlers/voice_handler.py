import os
import uuid
import logging
from pathlib import Path
from aiogram import Router, F, Bot, html
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.config import settings
from bot.database.db import get_session
from bot.database import crud
from bot.services.speech_to_text import transcribe_voice
from bot.services.intent_parser import parse_user_intent
from bot.keyboards.inline import get_entry_confirm_keyboard, get_tasks_keyboard
from bot.handlers.states import GarageEntryState
from bot.services.draft_store import save_draft
from bot.services.assistant import answer_query
from bot.services.formatters import send_formatted_message
from bot.emojis import (
    E_DROP,
    E_WRENCH,
    E_BOX,
    E_NOTE,
    E_LIST,
    E_MIC,
    E_MUTE,
    E_LOCK,
    E_SEARCH,
    E_ALERT,
    E_PARTY,
    E_THINK,
    E_QUESTION,
)

logger = logging.getLogger(__name__)

router = Router(name="voice_handler_router")


def format_markdown_card(intent: str, data: dict) -> str:
    """Форматирует карточку с распознанными данными в HTML c <tg-emoji>."""
    if intent == "fuel":
        liters = data.get("liters")
        cost = data.get("cost")
        odometer = data.get("odometer")
        station = data.get("station")

        liters_str = f"{liters} л" if liters is not None else "не указано"
        cost_str = f"{cost:,.0f} ₽".replace(",", " ") if cost is not None else "не указано"
        odo_str = f"{odometer:,} км".replace(",", " ") if odometer is not None else "не указан"
        station_str = str(station) if station else "не указана"

        return (
            f"{E_DROP} <b>Распознана заправка:</b>\n\n"
            f"• <b>Литры:</b> <code>{liters_str}</code>\n"
            f"• <b>Сумма:</b> <code>{cost_str}</code>\n"
            f"• <b>Пробег:</b> <code>{odo_str}</code>\n"
            f"• <b>АЗС:</b> <code>{station_str}</code>\n\n"
            "<i>Все верно? Нажми подтвердить для записи в журнал.</i>"
        )

    elif intent == "service":
        title = data.get("title") or "Техническое обслуживание"
        cost = data.get("cost")
        odometer = data.get("odometer")
        notes = data.get("notes")

        cost_str = f"{cost:,.0f} ₽".replace(",", " ") if cost is not None else "не указано"
        odo_str = f"{odometer:,} км".replace(",", " ") if odometer is not None else "не указан"

        text = (
            f"{E_WRENCH} <b>Распознано обслуживание / ремонт:</b>\n\n"
            f"• <b>Работы:</b> <b>{html.quote(str(title))}</b>\n"
            f"• <b>Пробег:</b> <code>{odo_str}</code>\n"
            f"• <b>Стоимость:</b> <code>{cost_str}</code>\n"
        )
        if notes:
            text += f"• <b>Заметки:</b> <i>{html.quote(str(notes))}</i>\n"
        text += "\n<i>Подтвердить внесение записи в журнал?</i>"
        return text

    elif intent == "item_save":
        item_name = data.get("item_name") or "Вещь"
        location = data.get("location") or "Гараж"

        return (
            f"{E_BOX} <b>Запомнить местоположение вещи:</b>\n\n"
            f"• <b>Предмет:</b> <b>{html.quote(str(item_name))}</b>\n"
            f"• <b>Где лежит:</b> <code>{html.quote(str(location))}</code>\n\n"
            "<i>Записать в каталог гаража?</i>"
        )

    elif intent == "task_save":
        title = data.get("title") or "Задача"
        due_date = data.get("due_date")
        due_str = f"• <b>Срок:</b> <code>{html.quote(str(due_date))}</code>\n" if due_date else ""

        return (
            f"{E_NOTE} <b>Новая задача / список дел:</b>\n\n"
            f"• <b>Дело:</b> <b>{html.quote(str(title))}</b>\n"
            f"{due_str}\n"
            "<i>Добавить это в твой список задач?</i>"
        )

    return f"ℹ️ <b>Распознаны данные:</b>\n{html.quote(str(data))}"


@router.message(F.voice)
async def handle_voice_entry(message: Message, bot: Bot, state: FSMContext):
    """
    Обработчик голосовых сообщений.
    1. Проверяет права доступа по ALLOWED_TELEGRAM_IDS.
    2. Отправляет временное сообщение с анимацией/статусом.
    3. Скачивает voice во временную папку temp/.
    4. Транскрибирует через Groq Whisper и парсит интент через Groq LLM.
    5. Выполняет ветвление (item_find, fuel/service/item_save, unknown).
    """
    user_id = message.from_user.id

    # Проверка доступа к боту
    if settings.ALLOWED_TELEGRAM_IDS and user_id not in settings.ALLOWED_TELEGRAM_IDS:
        await message.answer(f"{E_LOCK} <b>Доступ ограничен.</b> Ваш ID отсутствует в списке доверенных.")
        return

    # Временное сообщение
    status_msg = await message.answer(f"{E_MIC} <i>Слушаю и расшифровываю...</i>")

    # Скачивание файла в temp/
    temp_dir = Path("temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = str(temp_dir / f"voice_{uuid.uuid4().hex[:8]}.ogg")

    try:
        await bot.download(file=message.voice.file_id, destination=temp_file_path)

        # Распознавание речи (файл удаляется в finally блока transcribe_voice)
        transcript = await transcribe_voice(file_path=temp_file_path)

        if not transcript or not transcript.strip():
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.answer(f"{E_MUTE} Не удалось расслышать слова. Попробуй сказать еще раз чуть громче.")
            return

        # Загрузка недавней истории диалога для понимания контекста
        async with get_session() as session:
            history = await crud.get_recent_chat_history(session, user_id=user_id, limit=8)

        context_str = None
        if history:
            context_str = "\n".join([f"{h['role']}: {h['content'][:250]}" for h in history[-4:]])

        # Парсинг интента через Groq LLM с учетом контекста
        parsed_result = await parse_user_intent(transcript, context=context_str)
        intent = parsed_result.get("intent", "unknown")
        data = parsed_result.get("data", {})

        # Удаляем временное сообщение статуса
        try:
            await status_msg.delete()
        except Exception:
            pass

        # --- Ветка 1: Поиск вещи ---
        if intent == "item_find":
            query = data.get("search_query") or transcript
            async with get_session() as session:
                found_items = await crud.search_item_locations(session, user_id=user_id, query=query)

            if found_items:
                results = []
                for item in found_items:
                    date_str = item.updated_at.strftime("%d.%m.%Y")
                    results.append(f"{E_SEARCH} Найдено: <b>{html.quote(item.item_name)}</b> лежит в <code>{html.quote(item.location)}</code> (обновлено {date_str})")
                await message.answer("\n\n".join(results))
            else:
                await message.answer(f"{E_SEARCH} Ничего похожего в гараже не нашел.")

        # --- Ветка 2: Список задач ---
        elif intent == "task_list":
            async with get_session() as session:
                tasks = await crud.get_active_tasks(session, user_id=user_id)

            if tasks:
                lines = [f"{E_LIST} <b>Твой актуальный список дел и задач:</b>\n"]
                for idx, t in enumerate(tasks, 1):
                    due = f" <i>(срок: {html.quote(t.due_date)})</i>" if t.due_date else ""
                    lines.append(f"{idx}. <b>{html.quote(t.title)}</b>{due}")
                kb = get_tasks_keyboard(tasks)
                await message.answer("\n".join(lines), reply_markup=kb, parse_mode=ParseMode.HTML)
            else:
                await message.answer(f"{E_PARTY} <b>У тебя нет активных задач!</b> Все дела выполнены или еще не записаны.")

        # --- Ветка 3: Заправка, сервис, сохранение вещи, задача ---
        elif intent in ["fuel", "service", "item_save", "task_save"]:
            # Сохранение в изолированное хранилище черновиков по draft_id
            draft_id = save_draft(user_id=user_id, intent=intent, data=data)

            # Дополнительное сохранение в FSM (дублирование для надежности)
            await state.set_state(GarageEntryState.waiting_confirmation)
            await state.update_data(
                intent=intent,
                payload=data,
                transcript=transcript,
                draft_id=draft_id,
                **data
            )

            card_text = format_markdown_card(intent=intent, data=data)
            await message.answer(
                card_text,
                reply_markup=get_entry_confirm_keyboard(draft_id=draft_id),
                parse_mode=ParseMode.HTML
            )

        # --- Ветка 4: Ответ ассистента (вопросы, советы, поиск в интернете) ---
        elif intent == "ask_assistant":
            needs_web = bool(data.get("needs_web_search"))
            search_query = data.get("search_query")
            user_query = data.get("user_query") or transcript

            wait_text = f"{E_SEARCH} <i>Ищу информацию в интернете...</i>" if needs_web else f"{E_THINK} <i>Думаю над ответом...</i>"
            assistant_wait_msg = await message.answer(wait_text)
            try:
                answer = await answer_query(
                    user_query=user_query,
                    needs_web=needs_web,
                    search_query=search_query,
                    history=history
                )
                try:
                    await assistant_wait_msg.delete()
                except Exception:
                    pass
                await send_formatted_message(message, answer)

                # Сохраняем реплику и ответ в историю диалога
                async with get_session() as session:
                    await crud.add_chat_message(session, user_id=user_id, role="user", content=user_query)
                    await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer)

            except Exception as err:
                logger.error(f"Ошибка при формировании ответа ассистента: {err}", exc_info=True)
                try:
                    await assistant_wait_msg.delete()
                except Exception:
                    pass
                await message.answer(f"{E_ALERT} Не удалось получить ответ ассистента. Попробуй переформулировать вопрос.")

        # --- Ветка 5: Не удалось распознать (шум) ---
        else:
            if transcript and len(transcript.strip()) > 3:
                assistant_wait_msg = await message.answer(f"{E_THINK} <i>Секунду...</i>")
                try:
                    answer = await answer_query(user_query=transcript, needs_web=False, history=history)
                    try:
                        await assistant_wait_msg.delete()
                    except Exception:
                        pass
                    await send_formatted_message(message, answer)

                    async with get_session() as session:
                        await crud.add_chat_message(session, user_id=user_id, role="user", content=transcript)
                        await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer)

                except Exception:
                    try:
                        await assistant_wait_msg.delete()
                    except Exception:
                        pass
                    await message.answer(
                        f"{E_QUESTION} Не удалось разобрать голосовое: «{html.quote(transcript)}». Попробуй сказать еще раз."
                    )
            else:
                await message.answer(f"{E_MUTE} Не удалось расслышать слова. Попробуй сказать еще раз.")

    except Exception as e:
        logger.error(f"Ошибка при обработке голосового сообщения: {e}", exc_info=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(
            f"{E_ALERT} Произошла ошибка при обработке голосового сообщения. Пожалуйста, попробуй еще раз."
        )

