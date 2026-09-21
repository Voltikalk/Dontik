import os
import uuid
import logging
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.config import settings
from bot.database.db import get_session
from bot.database import crud
from bot.services.speech_to_text import transcribe_voice
from bot.services.intent_parser import parse_user_intent
from bot.keyboards.inline import get_entry_confirm_keyboard
from bot.handlers.states import GarageEntryState

logger = logging.getLogger(__name__)

router = Router(name="voice_handler_router")


def format_markdown_card(intent: str, data: dict) -> str:
    """Форматирует карточку с распознанными данными в Markdown."""
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
            "⛽ *Распознана заправка:*\n\n"
            f"• *Литры:* {liters_str}\n"
            f"• *Сумма:* {cost_str}\n"
            f"• *Пробег:* {odo_str}\n"
            f"• *АЗС:* {station_str}\n\n"
            "_Все верно? Нажми подтвердить для записи в журнал._"
        )

    elif intent == "service":
        title = data.get("title") or "Техническое обслуживание"
        cost = data.get("cost")
        odometer = data.get("odometer")
        notes = data.get("notes")

        cost_str = f"{cost:,.0f} ₽".replace(",", " ") if cost is not None else "не указано"
        odo_str = f"{odometer:,} км".replace(",", " ") if odometer is not None else "не указан"

        text = (
            "🔧 *Распознано обслуживание / ремонт:*\n\n"
            f"• *Работы:* {title}\n"
            f"• *Пробег:* {odo_str}\n"
            f"• *Стоимость:* {cost_str}\n"
        )
        if notes:
            text += f"• *Заметки:* {notes}\n"
        text += "\n_Подтвердить внесение записи в журнал?_"
        return text

    elif intent == "item_save":
        item_name = data.get("item_name") or "Вещь"
        location = data.get("location") or "Гараж"

        return (
            "📦 *Запомнить местоположение вещи:*\n\n"
            f"• *Предмет:* {item_name}\n"
            f"• *Где лежит:* {location}\n\n"
            "_Записать в каталог гаража?_"
        )

    elif intent == "task_save":
        title = data.get("title") or "Задача"
        due_date = data.get("due_date")
        due_str = f"• *Срок:* {due_date}\n" if due_date else ""

        return (
            "📝 *Новая задача / список дел:*\n\n"
            f"• *Дело:* {title}\n"
            f"{due_str}\n"
            "_Добавить это в твой список задач?_"
        )

    return "ℹ️ *Распознаны данные:*\n" + str(data)


@router.message(F.voice)
async def handle_voice_entry(message: Message, bot: Bot, state: FSMContext):
    """
    Обработчик голосовых сообщений.
    1. Проверяет права доступа по ALLOWED_TELEGRAM_IDS.
    2. Отправляет временное сообщение '🎙 Слушаю и расшифровываю...'.
    3. Скачивает voice во временную папку temp/.
    4. Транскрибирует через Groq Whisper и парсит интент через Groq LLM.
    5. Выполняет ветвление (item_find, fuel/service/item_save, unknown).
    """
    user_id = message.from_user.id

    # Проверка доступа к боту
    if settings.ALLOWED_TELEGRAM_IDS and user_id not in settings.ALLOWED_TELEGRAM_IDS:
        await message.answer("⛔ Доступ ограничен. Ваш ID отсутствует в списке доверенных.")
        return

    # Временное сообщение
    status_msg = await message.answer("🎙 Слушаю и расшифровываю...")

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
            await message.answer("🔇 Не удалось расслышать слова. Попробуй сказать еще раз чуть громче.")
            return

        # Парсинг интента через Groq LLM
        parsed_result = await parse_user_intent(transcript)
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
                    results.append(f"🔍 Найдено: {item.item_name} лежит в {item.location} (обновлено {date_str})")
                await message.answer("\n\n".join(results))
            else:
                await message.answer("Ничего похожего в гараже не нашел")

        # --- Ветка 2: Список задач ---
        elif intent == "task_list":
            async with get_session() as session:
                tasks = await crud.get_active_tasks(session, user_id=user_id)

            if tasks:
                lines = ["📋 *Твой актуальный список дел и задач:*\n"]
                for idx, t in enumerate(tasks, 1):
                    due = f" _(срок: {t.due_date})_" if t.due_date else ""
                    lines.append(f"{idx}. {t.title}{due}")
                await message.answer("\n".join(lines), parse_mode="Markdown")
            else:
                await message.answer("🎉 У тебя нет активных задач! Все дела выполнены или еще не записаны.")

        # --- Ветка 3: Заправка, сервис, сохранение вещи, задача ---
        elif intent in ["fuel", "service", "item_save", "task_save"]:
            # Сохранение спарсенных данных в FSM
            await state.set_state(GarageEntryState.waiting_confirmation)
            await state.update_data(intent=intent, data=data, transcript=transcript)

            card_text = format_markdown_card(intent=intent, data=data)
            await message.answer(
                card_text,
                reply_markup=get_entry_confirm_keyboard(),
                parse_mode="Markdown"
            )

        # --- Ветка 4: Не удалось распознать ---
        else:
            await message.answer(
                f"Не удалось точно понять данные. Распознанный текст: «{transcript}». Попробуй сказать еще раз."
            )

    except Exception as e:
        logger.error(f"Ошибка при обработке голосового сообщения: {e}", exc_info=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(
            "⚠️ Произошла ошибка при обработке голосового сообщения. Пожалуйста, попробуй еще раз."
        )
