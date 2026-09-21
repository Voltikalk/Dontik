import logging
from aiogram import Router, html, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.db import get_session
from bot.database import crud
from bot.keyboards.inline import get_tasks_keyboard, get_entry_confirm_keyboard
from bot.services.intent_parser import parse_user_intent
from bot.services.assistant import answer_query
from bot.services.draft_store import save_draft
from bot.handlers.voice_handler import format_markdown_card
from bot.handlers.states import GarageEntryState
from bot.services.formatters import send_formatted_message
from bot.services.agents import MultiAgentOrchestrator

logger = logging.getLogger(__name__)

orchestrator = MultiAgentOrchestrator()

router = Router(name="general_handler_router")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    Приветствие по имени и подсказка по использованию голосового ввода.
    """
    first_name = message.from_user.first_name or "Автомобилист"
    safe_name = html.quote(first_name)

    text = (
        f"👋 <b>Привет, {safe_name}!</b>\n\n"
        "Я твой личный универсальный помощник, задачник и авто-гаражный ассистент.\n\n"
        "🎙 <b>Ты можешь писать текстом или просто зажать микрофон:</b>\n"
        "• 📝 <b>Задачи:</b> <i>«Запиши на завтра съездить на дачу, купить грабли»</i>\n"
        "• 🌐 <b>Поиск в сети:</b> <i>«Какая погода завтра в Самаре?»</i> или <i>«Курс доллара»</i>\n"
        "• 💡 <b>Советы и вопросы:</b> <i>«Как прокачать тормоза на Ниве?»</i>\n"
        "• ⛽ <b>Заправки:</b> <i>«Заправил 35 литров на две тысячи, пробег 150 000»</i>\n"
        "• 📦 <b>Вещи:</b> <i>«Положил домкрат под верстак»</i> / <i>«Где лежит домкрат?»</i>\n"
        "• 📄 <b>Документы:</b> отправляй PDF, Word (.docx), Excel (.xlsx, .csv), TXT для анализа\n"
        "• 🖼 <b>Фотографии:</b> присылай фото деталей, чеков, приборов, схем или предметов\n"
        "• 🤖 <b>Субагенты:</b> <code>/agent</code> — запуск команды субагентов для глубокого разбора\n\n"
        "📌 <b>Быстрые команды:</b>\n"
        "/agent — глубокое исследование задачи командой субагентов\n"
        "/tasks — список актуальных задач с кнопками выполнения\n"
        "/stats — сводка по заправкам и ремонтам\n"
        "/items — каталог вещей в гараже\n"
        "/clear — сбросить контекст диалога\n"
        "/help — подробная справка"
    )
    await message.answer(text)


@router.message(Command("agent", "research"))
async def cmd_agent(message: Message):
    """
    Обработчик команды /agent или /research для запуска мультиагентной системы.
    """
    user_id = message.from_user.id
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        help_text = (
            "🤖 <b>Команда субагентов (Multi-Agent System)</b>\n\n"
            "Запускает совместную работу специализированных субагентов для глубокого решения задачи:\n"
            "• 🔍 <b>Поиск и аналитика</b> — мониторинг цен, артикулов и предложений в сети\n"
            "• 🔧 <b>Технический эксперт</b> — регламенты, инструмент, моменты затяжки, нюансы ремонта\n"
            "• 📊 <b>Сметы и расчеты</b> — финансовая калькуляция, аудит расходов, сравнение смет\n"
            "• 📋 <b>Планировщик</b> — пошаговый чек-лист этапов и временные оценки\n\n"
            "💡 <b>Примеры запуска:</b>\n"
            "<code>/agent Замена сцепления на ВАЗ 2121 Нива: регламент, цены на комплект Valeo и пошаговый план</code>\n\n"
            "<code>/agent Капитальный ремонт дачной беседки: смета материалов, закупка и этапы</code>"
        )
        await message.answer(help_text)
        return

    task = parts[1].strip()
    status_msg = await message.answer("🤖 <i>Запуск команды субагентов...</i>")

    async def update_progress(msg: str):
        try:
            await status_msg.edit_text(msg)
        except Exception:
            pass

    try:
        async with get_session() as session:
            history = await crud.get_recent_chat_history(session, user_id=user_id, limit=3)

        context = {}
        if history:
            context["history"] = history

        final_report = await orchestrator.execute_task(
            task=task,
            context=context,
            on_progress=update_progress
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

        await send_formatted_message(message, final_report)

        # Сохраняем в историю диалога
        async with get_session() as session:
            await crud.add_chat_message(session, user_id=user_id, role="user", content=f"/agent {task}")
            await crud.add_chat_message(session, user_id=user_id, role="assistant", content=final_report)

    except Exception as e:
        logger.error(f"Ошибка при работе субагентов: {e}", exc_info=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(f"⚠️ Ошибка при выполнении задачи субагентами: {e}")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """
    Обработчик команды /stats.
    Выводит сводку по последней заправке и последнему ремонту.
    """
    user_id = message.from_user.id

    async with get_session() as session:
        last_fuel = await crud.get_last_fuel_log(session, user_id=user_id)
        last_service = await crud.get_last_service_log(session, user_id=user_id)

    lines = ["📊 <b>Сводка по автомобилю:</b>\n"]

    # Блок последней заправки
    if last_fuel:
        fuel_date = last_fuel.date.strftime("%d.%m.%Y")
        station_str = f" (АЗС: {html.quote(last_fuel.station_name)})" if last_fuel.station_name else ""
        lines.append(
            f"⛽ <b>Последняя заправка ({fuel_date}):</b>\n"
            f"• Объем: <code>{last_fuel.liters:.1f} л</code>\n"
            f"• Стоимость: <code>{last_fuel.cost:,.0f} ₽</code>\n"
            f"• Пробег: <code>{last_fuel.odometer:,} км</code>{station_str}\n".replace(",", " ")
        )
    else:
        lines.append("⛽ <b>Последняя заправка:</b> <i>записей пока нет</i>\n")

    # Блок последнего сервиса / ТО
    if last_service:
        service_date = last_service.date.strftime("%d.%m.%Y")
        cost_str = f" на <code>{last_service.cost:,.0f} ₽</code>" if last_service.cost else ""
        notes_str = f"\n• Заметки: <i>{html.quote(last_service.notes)}</i>" if last_service.notes else ""
        lines.append(
            f"🔧 <b>Последнее ТО / ремонт ({service_date}):</b>\n"
            f"• Работы: <b>{html.quote(last_service.title)}</b>{cost_str}\n"
            f"• Пробег: <code>{last_service.odometer:,} км</code>{notes_str}\n".replace(",", " ")
        )
    else:
        lines.append("🔧 <b>Последнее ТО / ремонт:</b> <i>записей пока нет</i>\n")

    await message.answer("\n".join(lines))


@router.message(Command("tasks", "todo"))
async def cmd_tasks(message: Message):
    """
    Обработчик команды /tasks и /todo.
    Выводит список активных задач пользователя.
    """
    user_id = message.from_user.id

    async with get_session() as session:
        tasks = await crud.get_active_tasks(session, user_id=user_id)

    if not tasks:
        await message.answer(
            "🎉 <b>Список задач пуст!</b>\n\n"
            "Чтобы добавить дело или покупку, просто скажите голосовым сообщением, например:\n"
            "<i>«Запиши на завтра съездить на дачу, купить грабли»</i>"
        )
        return

    lines = ["📋 <b>Твой актуальный список дел и задач:</b>\n"]
    for idx, t in enumerate(tasks, 1):
        due_str = f" <i>(срок: {html.quote(t.due_date)})</i>" if t.due_date else ""
        lines.append(f"{idx}. <b>{html.quote(t.title)}</b>{due_str}")

    kb = get_tasks_keyboard(tasks)
    await message.answer("\n".join(lines), reply_markup=kb)


@router.message(Command("items", "garage"))
async def cmd_items(message: Message):
    """
    Обработчик команды /items и /garage.
    Выводит список сохраненных вещей в гараже/на даче.
    """
    user_id = message.from_user.id
    async with get_session() as session:
        items = await crud.list_all_items(session, user_id=user_id)

    if not items:
        await message.answer(
            "📦 <b>В гараже пока ничего не записано.</b>\n\n"
            "Чтобы сохранить местоположение вещи, просто скажите голосовым сообщением, например:\n"
            "<i>«Положил домкрат под верстак»</i>"
        )
        return

    lines = ["📦 <b>Список вещей на хранении:</b>\n"]
    for idx, it in enumerate(items, 1):
        lines.append(f"{idx}. <b>{html.quote(it.item_name)}</b> — <code>{html.quote(it.location)}</code>")
    lines.append("\n💡 <i>Чтобы найти конкретную вещь, спросите голосовым: «Где лежит ...?»</i>")
    await message.answer("\n".join(lines))


@router.message(Command("help"))
async def cmd_help(message: Message):
    """
    Обработчик команды /help.
    Справочная информация и примеры использования.
    """
    text = (
        "💡 <b>Как пользоваться ботом «Авто-Гараж и Персональный Ассистент»:</b>\n\n"
        "🎙 <b>Голосовое и текстовое управление:</b>\n"
        "Вы можете как зажать кнопку микрофона, так и просто написать текст в чат:\n\n"
        "📝 <b>Задачи и напоминания:</b>\n"
        "• <i>«Запиши на завтра съездить на работу к Николаю Викторовичу»</i>\n"
        "• <i>«Напомни в субботу поменять масло»</i>\n"
        "• <i>«Какие у меня дела?»</i> (выведет список задач с кнопками завершения)\n\n"
        "🌐 <b>Поиск в интернете (подключается автоматически):</b>\n"
        "• <i>«Какая погода завтра в Москве?»</i>\n"
        "• <i>«Найди актуальный курс доллара и евро»</i>\n"
        "• <i>«Сколько стоит резина 205/55 R16?»</i>\n\n"
        "💡 <b>Вопросы, математика и экспертные советы:</b>\n"
        "• <i>«Реши уравнение x^2 = 38»</i>\n"
        "• <i>«А почему два корня?»</i> (бот помнит контекст прошлых вопросов!)\n"
        "• <i>«Как прокачать тормоза на классике?»</i>\n\n"
        "📄 <b>Анализ документов (PDF, Word, Excel, CSV, TXT):</b>\n"
        "• Отправьте файл боту (можно с вопросом в подписи, например: <i>«Сделай краткое резюме»</i>, <i>«Посчитай итог по расходам»</i>)\n"
        "• Бот извлечет текст и таблицы и даст подробный ответ.\n\n"
        "🖼 <b>Распознавание фотографий (Vision):</b>\n"
        "• Отправьте фото автозапчасти, приборной панели, чека, схемы или инструмента — бот определит детали, распознает текст, маркировку и ответит на вопросы.\n\n"
        "⛽ <b>Заправки автомобиля:</b>\n"
        "• <i>«Заправил сорок литров на 2500 рублей, пробег 155 000, Газпромнефть»</i>\n\n"
        "🔧 <b>Сервис и ремонты:</b>\n"
        "• <i>«Поменял тормозные диски и колодки, отдал 8000 руб, пробег 156 000»</i>\n\n"
        "📦 <b>Поиск и хранение вещей:</b>\n"
        "• <i>«Положил зарядник для аккумулятора в синий ящик»</i>\n"
        "• <i>«Где лежит зарядник?»</i>\n\n"
        "🤖 <b>Команда субагентов (Multi-Agent System):</b>\n"
        "• <code>/agent &lt;задача&gt;</code> — запускает команду узких специалистов (поиск цен, техэкспертиза, расчет сметы и пошаговый план) для глубокого решения комплексных задач.\n\n"
        "📌 <b>Быстрые команды из меню ввода:</b>\n"
        "/agent — запуск команды субагентов для глубокого разбора\n"
        "/tasks — актуальный список дел\n"
        "/stats — сводка по заправкам и ремонтам\n"
        "/items — каталог вещей в гараже\n"
        "/clear — сбросить контекст диалога (начать заново)\n"
        "/help — подробная справка\n"
        "/start — главное меню"
    )
    await message.answer(text)


@router.message(Command("clear"))
@router.message(Command("reset"))
async def cmd_clear_history(message: Message):
    """
    Обработчик команды /clear и /reset.
    Очищает историю диалога пользователя (память контекста).
    """
    user_id = message.from_user.id
    async with get_session() as session:
        await crud.clear_chat_history(session, user_id=user_id)
    await message.answer("🔄 <b>Память диалога очищена.</b>\nЗадавай новый вопрос — я готов к новой теме!")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message, state: FSMContext):
    """
    Универсальный обработчик обычных текстовых сообщений.
    Позволяет вводить задачи, вести учет расходов и задавать любые вопросы
    текстом точно так же, как и голосом, с полной поддержкой памяти диалога.
    """
    user_id = message.from_user.id
    raw_text = message.text.strip()
    if not raw_text:
        return

    lowered = raw_text.lower()

    # 1. Быстрые команды на естественном языке
    if lowered in {"меню", "start", "старт"}:
        await cmd_start(message)
        return
    elif lowered in {"задачи", "дела", "список задач", "список дел", "что сделать", "планы"}:
        await cmd_tasks(message)
        return
    elif lowered in {"почта", "проверь почту", "что на почте", "новые письма", "письма", "входящие письма", "проверить почту"}:
        from bot.handlers.email_handler import cmd_check_mail
        await cmd_check_mail(message)
        return
    elif lowered in {"статистика", "статы", "расходы", "заправки"}:
        await cmd_stats(message)
        return
    elif lowered in {"вещи", "гараж", "инвентарь", "где что лежит"}:
        await cmd_items(message)
        return
    elif lowered in {"помощь", "справка", "help", "инструкция"}:
        await cmd_help(message)
        return
    elif lowered in {"забудь", "сброс", "очисти диалог", "очисти контекст", "сбрось контекст", "начнем заново", "очистить память", "забудь все"}:
        await cmd_clear_history(message)
        return

    # 2. Загрузка недавней истории диалога для контекста
    async with get_session() as session:
        history = await crud.get_recent_chat_history(session, user_id=user_id, limit=8)

    context_str = None
    if history:
        context_str = "\n".join([f"{h['role']}: {h['content'][:250]}" for h in history[-4:]])

    # 3. Интеллектуальный разбор интента через Groq LLM с учетом контекста
    parsed = await parse_user_intent(raw_text, context=context_str)
    intent = parsed.get("intent", "unknown")
    data = parsed.get("data", {})

    # Ветка: Поиск вещи
    if intent == "item_find":
        query = data.get("search_query") or raw_text
        async with get_session() as session:
            found = await crud.search_item_locations(session, user_id=user_id, query=query)
        if found:
            results = []
            for it in found:
                date_str = it.updated_at.strftime("%d.%m.%Y")
                results.append(f"🔍 Найдено: <b>{html.quote(it.item_name)}</b> лежит в <code>{html.quote(it.location)}</code> (обновлено {date_str})")
            await message.answer("\n\n".join(results))
        else:
            await message.answer("Ничего похожего в гараже не нашел.")

    # Ветка: Список задач
    elif intent == "task_list":
        await cmd_tasks(message)

    # Ветка: Заправка, сервис, вещь, задача (карточка подтверждения)
    elif intent in ["fuel", "service", "item_save", "task_save"]:
        draft_id = save_draft(user_id=user_id, intent=intent, data=data)
        await state.set_state(GarageEntryState.waiting_confirmation)
        await state.update_data(
            intent=intent,
            payload=data,
            transcript=raw_text,
            draft_id=draft_id,
            **data
        )
        card_text = format_markdown_card(intent=intent, data=data)
        await message.answer(
            card_text,
            reply_markup=get_entry_confirm_keyboard(draft_id=draft_id),
            parse_mode="Markdown"
        )

    # Ветка: Универсальный ассистент и веб-поиск
    elif intent == "ask_assistant":
        needs_web = bool(data.get("needs_web_search"))
        search_query = data.get("search_query")
        user_query = data.get("user_query") or raw_text

        status_text = "🔍 <i>Ищу актуальную информацию в интернете...</i>" if needs_web else "🤔 <i>Думаю над ответом...</i>"
        status_msg = await message.answer(status_text)
        try:
            answer = await answer_query(
                user_query=user_query,
                needs_web=needs_web,
                search_query=search_query,
                history=history
            )
            try:
                await status_msg.delete()
            except Exception:
                pass
            await send_formatted_message(message, answer)

            # Сохраняем диалог в память
            async with get_session() as session:
                await crud.add_chat_message(session, user_id=user_id, role="user", content=user_query)
                await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer)

        except Exception as e:
            logger.error(f"Ошибка ассистента при текстовом запросе: {e}", exc_info=True)
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.answer("⚠️ Не удалось получить ответ. Попробуй переформулировать вопрос.")

    # Ветка: Общий диалог / неопределенный текст
    else:
        status_msg = await message.answer("🤔 <i>Секунду...</i>")
        try:
            answer = await answer_query(user_query=raw_text, needs_web=False, history=history)
            try:
                await status_msg.delete()
            except Exception:
                pass
            await send_formatted_message(message, answer)

            # Сохраняем диалог в память
            async with get_session() as session:
                await crud.add_chat_message(session, user_id=user_id, role="user", content=raw_text)
                await crud.add_chat_message(session, user_id=user_id, role="assistant", content=answer)

        except Exception:
            try:
                await status_msg.delete()
            except Exception:
                pass
            await message.answer("Я не совсем понял, что требуется сделать. Напиши вопрос подробнее или нажми /help.")




