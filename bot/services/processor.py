import logging
from aiogram.types import Message
from aiogram import html

from bot.database.db import get_session
from bot.database import crud
from bot.services.intent_parser import parse_user_intent
from bot.services.draft_store import save_draft
from bot.services.formatters import (
    format_fuel_card,
    format_service_card,
    format_location_card,
    format_found_items,
    format_stats_summary,
    format_all_items_list,
    format_fuel_history,
    format_service_history
)
from bot.keyboards.inline import get_confirm_keyboard, get_main_menu_keyboard

logger = logging.getLogger(__name__)


async def process_user_intent(message: Message, text: str, is_voice: bool = False):
    """
    Универсальный обработчик текста/транскрипции через Groq LLM
    с формированием интерактивных карточек подтверждения.
    """
    user_id = message.from_user.id
    raw_quote = text if is_voice else ""

    try:
        parsed = await parse_user_intent(text)
    except Exception as e:
        logger.error(f"Ошибка вызова LLM парсера: {e}", exc_info=True)
        await message.answer(
            "⚠️ <b>Произошла ошибка при обращении к искусственному интеллекту.</b>\n"
            "Пожалуйста, проверьте настройки ключа <code>GROQ_API_KEY</code> в файле <code>.env</code>."
        )
        return

    intent = parsed.get("intent", "unknown")
    data = parsed.get("data", {})

    if intent in {"fuel", "fuel_log"}:
        draft_id = save_draft(user_id=user_id, intent="fuel", data=data)
        card_text = format_fuel_card(data=data, raw_text=raw_quote)
        await message.answer(card_text, reply_markup=get_confirm_keyboard("fuel", draft_id))

    elif intent in {"service", "service_log"}:
        draft_id = save_draft(user_id=user_id, intent="service", data=data)
        card_text = format_service_card(data=data, raw_text=raw_quote)
        await message.answer(card_text, reply_markup=get_confirm_keyboard("service", draft_id))

    elif intent in {"item_save", "set_location"}:
        draft_id = save_draft(user_id=user_id, intent="item_save", data=data)
        card_text = format_location_card(data=data, raw_text=raw_quote)
        await message.answer(card_text, reply_markup=get_confirm_keyboard("item", draft_id))

    elif intent in {"item_find", "find_location"}:
        query = data.get("search_query") or data.get("item_name") or text
        async with get_session() as session:
            items = await crud.search_item_locations(session, user_id=user_id, query=query)
        result_text = format_found_items(items, query=query)
        await message.answer(result_text)

    else:
        # Неизвестный интент или общий вопрос
        reply_text = (
            "🤔 Не удалось однозначно распознать команду для автомобиля или гаража.\n\n"
            "💡 <b>Вы можете сказать или написать:</b>\n"
            "• <i>«Заправил 35 литров на 2000 рублей, пробег 115000»</i>\n"
            "• <i>«Поменял свечи зажигания, отдал 3000 руб»</i>\n"
            "• <i>«Положил компрессор в багажник»</i>\n"
            "• <i>«Где лежит компрессор?»</i>"
        )
        if is_voice and raw_quote:
            reply_text = f"<blockquote expandable>🗣 <b>Распознано:</b>\n{html.quote(raw_quote)}</blockquote>\n\n{reply_text}"
        await message.answer(reply_text, reply_markup=get_main_menu_keyboard())
