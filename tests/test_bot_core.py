"""Интеграционные проверки: БД, миграции, CRUD, разбор карточек, даты, клавиатуры."""

import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --- Фикстура с временной БД ---

@pytest.fixture()
async def temp_db(monkeypatch):
    """Изолированная SQLite в tmp, чтобы тесты не трогали data/garage.db."""
    import bot.database.db as db_module  # регистрирует Юникод-lower/LIKE для SQLite
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from bot.database import crud
    from bot.database.models import Base

    assert db_module is not None

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        class _Ctx:
            async def __aenter__(self):
                self.session = factory()
                return self.session

            async def __aexit__(self, exc_type, exc, tb):
                if exc_type is None:
                    await self.session.commit()
                else:
                    await self.session.rollback()
                await self.session.close()

        yield _Ctx, engine, crud

        await engine.dispose()


UID = 424242


# --- CRUD: задачи ---

@pytest.mark.asyncio
async def test_task_due_at_and_sorting(temp_db):
    ctx, engine, crud = temp_db

    async with ctx() as s:
        await crud.add_task(s, UID, "без срока", None, None)
        await crud.add_task(s, UID, "поздняя", "31.12.2026", datetime(2026, 12, 31, 9, 0))
        await crud.add_task(s, UID, "ранняя", "01.10.2026", datetime(2026, 10, 1, 9, 0))

    async with ctx() as s:
        tasks = await crud.get_active_tasks(s, user_id=UID)
    titles = [t.title for t in tasks]
    # Со сроком раньше, чем без срока; внутри — по возрастанию даты
    assert titles == ["ранняя", "поздняя", "без срока"]


@pytest.mark.asyncio
async def test_task_overdue_sorted_first(temp_db):
    ctx, engine, crud = temp_db
    past = datetime.now() - timedelta(days=3)

    async with ctx() as s:
        await crud.add_task(s, UID, "просроченная", "27.09.2026", past)
        await crud.add_task(s, UID, "будущая", "05.10.2026", datetime.now() + timedelta(days=5))

    async with ctx() as s:
        tasks = await crud.get_active_tasks(s, user_id=UID)
    assert tasks[0].title == "просроченная"


@pytest.mark.asyncio
async def test_complete_uncomplete_and_delete(temp_db):
    ctx, engine, crud = temp_db

    async with ctx() as s:
        task = await crud.add_task(s, UID, "купить масло")
        task_id = task.id

    async with ctx() as s:
        assert await crud.complete_task(s, user_id=UID, task_id=task_id) is True
    async with ctx() as s:
        assert await crud.get_active_tasks(s, user_id=UID) == []

    async with ctx() as s:
        assert await crud.uncomplete_task(s, user_id=UID, task_id=task_id) is True
    async with ctx() as s:
        tasks = await crud.get_active_tasks(s, user_id=UID)
    assert len(tasks) == 1

    async with ctx() as s:
        assert await crud.delete_task(s, user_id=UID, task_id=task_id) is True
    async with ctx() as s:
        assert await crud.get_active_tasks(s, user_id=UID) == []


@pytest.mark.asyncio
async def test_complete_all_tasks(temp_db):
    ctx, engine, crud = temp_db
    async with ctx() as s:
        for i in range(5):
            await crud.add_task(s, UID, f"задача {i}")

    async with ctx() as s:
        assert await crud.complete_all_tasks(s, user_id=UID) == 5
    async with ctx() as s:
        assert await crud.get_active_tasks(s, user_id=UID) == []


# --- CRUD: вещи и поиск ---

@pytest.mark.asyncio
async def test_item_search_ranking(temp_db):
    ctx, engine, crud = temp_db

    async with ctx() as s:
        await crud.upsert_item_location(s, UID, "Домкрат гидравлический", "верстак")
        await crud.upsert_item_location(s, UID, "Ключ на 13", "синий ящик")
        await crud.upsert_item_location(s, UID, "Съёмник подшипников", "третья полка")

    # Точное слово в начале приоритетнее вхождения в середине
    async with ctx() as s:
        found = await crud.search_item_locations(s, user_id=UID, query="Домкрат")
    assert found and "Домкрат" in found[0].item_name

    # Поиск по части слова со склонением
    async with ctx() as s:
        found = await crud.search_item_locations(s, user_id=UID, query="подшипник")
    assert found and "Съёмник" in found[0].item_name

    # Мусор не должен находиться
    async with ctx() as s:
        found = await crud.search_item_locations(s, user_id=UID, query="абракадабра")
    assert found == []


@pytest.mark.asyncio
async def test_item_upsert_updates_location(temp_db):
    ctx, engine, crud = temp_db
    async with ctx() as s:
        await crud.upsert_item_location(s, UID, "Компрессор", "стеллаж")
    async with ctx() as s:
        await crud.upsert_item_location(s, UID, "Компрессор", "верстак")

    async with ctx() as s:
        items = await crud.list_all_items(s, user_id=UID)
    assert len(items) == 1
    assert items[0].location == "верстак"


# --- CRUD: расход топлива ---

@pytest.mark.asyncio
async def test_avg_consumption_ignores_bad_odometer(temp_db):
    """
    Расход = литры последней заправки / расстояние с предыдущей.
    Записи с нелогичным одометром (прыжок назад или >3000 км) отбрасываются.
    """
    ctx, engine, crud = temp_db

    async with ctx() as s:
        await crud.add_fuel_log(s, UID, 40.0, 2400.0, 150000)
    async with ctx() as s:
        await crud.add_fuel_log(s, UID, 40.0, 2500.0, 150500)
    async with ctx() as s:
        await crud.add_fuel_log(s, UID, 10.0, 600.0, 5)  # одометр уехал назад — мусор

    async with ctx() as s:
        consumption = await crud.get_avg_consumption(s, user_id=UID)

    # Валидная пара: 40 л на 500 км = 8 л/100 км. Мусорный отброшен.
    assert consumption == 8.0


@pytest.mark.asyncio
async def test_avg_consumption_sums_multiple_fills(temp_db):
    ctx, engine, crud = temp_db

    async with ctx() as s:
        await crud.add_fuel_log(s, UID, 40.0, 2400.0, 150000)
    async with ctx() as s:
        await crud.add_fuel_log(s, UID, 40.0, 2500.0, 150500)
    async with ctx() as s:
        await crud.add_fuel_log(s, UID, 40.0, 2600.0, 151000)

    async with ctx() as s:
        consumption = await crud.get_avg_consumption(s, user_id=UID)

    # Две валидные заправки по 40 л на 500 км каждая: 80 л / 1000 км = 8 л/100 км
    assert consumption == 8.0


@pytest.mark.asyncio
async def test_avg_consumption_needs_two_points(temp_db):
    ctx, engine, crud = temp_db
    async with ctx() as s:
        await crud.add_fuel_log(s, UID, 40.0, 2400.0, 150000)
    async with ctx() as s:
        assert await crud.get_avg_consumption(s, user_id=UID) is None


# --- Карточки подтверждения ---

def test_cards_show_expandable_transcript():
    """Голосовой ввод должен показывать, что именно бот услышал."""
    from bot.services.formatters import (
        format_fuel_card,
        format_item_card,
        format_service_card,
        format_task_card,
    )

    transcript = "заправил сорок два с половиной литра на две с половиной тысячи"
    for card in (
        format_fuel_card({"liters": 42.5, "cost": 2500, "odometer": 154300, "station": "Лукойл"}, transcript),
        format_service_card({"title": "масло", "cost": 6200, "odometer": 155000}, transcript),
        format_item_card({"item_name": "домкрат", "location": "верстак"}, transcript),
        format_task_card({"title": "купить грабли", "due_date": "завтра"}, transcript),
    ):
        assert "<blockquote expandable>" in card
        assert "услышал" in card.lower()

    # Текстовый ввод не должен получать блок «услышал»
    assert "<blockquote expandable>" not in format_fuel_card({"liters": 40, "cost": 2400}, "")


def test_fuel_card_computes_price_per_liter():
    from bot.services.formatters import format_fuel_card

    card = format_fuel_card({"liters": 50, "cost": 3000, "odometer": 1000, "station": None})
    assert "60.00" in card  # 3000 / 50
    assert "не указана" in card  # АЗС не названа


def test_cards_escape_user_input():
    """Пользовательский ввод не должен ломать HTML Telegram."""
    from bot.services.formatters import format_item_card, format_task_card

    card = format_item_card({"item_name": "<b>жирный</b> & \"кавычки\"", "location": "a<b"})
    assert "&lt;b&gt;" in card
    assert "<b>жирный</b>" not in card

    card = format_task_card({"title": "5 < 10 > 3", "due_date": None})
    assert "5 &lt; 10" in card


def test_cards_handle_missing_fields():
    """Отсутствующие поля не должны ронять карточку."""
    from bot.services.formatters import (
        format_fuel_card,
        format_item_card,
        format_service_card,
        format_task_card,
    )

    assert format_fuel_card({}, "")
    assert format_service_card({}, "")
    assert format_item_card({}, "")
    assert format_task_card({}, "")
    # Нули считаются отсутствием, а не делением на ноль
    assert format_fuel_card({"liters": 0, "cost": 0}, "")


def test_tasks_list_marks_overdue():
    from bot.services.formatters import format_tasks_list

    class FakeTask:
        def __init__(self, i, title, due_at=None, due_date=None):
            self.id = i
            self.title = title
            self.due_at = due_at
            self.due_date = due_date

    tasks = [
        FakeTask(1, "просроченная", datetime.now() - timedelta(days=2), "28.09.2026"),
        FakeTask(2, "будущая", datetime.now() + timedelta(days=5), "05.10.2026"),
        FakeTask(3, "без срока", None, None),
    ]
    text = format_tasks_list(tasks)
    assert "просрочено" in text
    assert "28.09.2026" in text
    # Без срока — просто строка без пометки
    assert "без срока" in text


# --- Естественные команды ---

def test_natural_command_matching():
    from bot.handlers.general_handler import _match_natural_command

    assert _match_natural_command("задачи") == "tasks"
    assert _match_natural_command("список задач") == "tasks"
    assert _match_natural_command("что сделать") == "tasks"
    assert _match_natural_command("статистика") == "stats"
    assert _match_natural_command("расходы") == "stats"
    assert _match_natural_command("гараж") == "items"
    assert _match_natural_command("письма") == "mail"
    assert _match_natural_command("помощь") == "help"
    assert _match_natural_command("сбрось контекст") == "clear"
    assert _match_natural_command("меню") == "start"
    # Обычная фраза не должна превращаться в команду
    assert _match_natural_command("запиши купить масло") is None
    assert _match_natural_command("реши уравнение x2=4") is None
    assert _match_natural_command("") is None


# --- Кириллица в SQLite ---

@pytest.mark.asyncio
async def test_sqlite_lower_handles_cyrillic(temp_db):
    """
    Регрессия: встроенная lower() в SQLite работает только с ASCII,
    из-за чего «Компрессор» и «компрессор» считались разными предметами.
    """
    ctx, engine, crud = temp_db
    from sqlalchemy import text

    async with engine.begin() as conn:
        assert (await conn.execute(text("SELECT lower('КомПРессор')"))).scalar() == "компрессор"
        assert (await conn.execute(text("SELECT lower('ДОМКРАТ')"))).scalar() == "домкрат"
        assert (await conn.execute(
            text("SELECT lower('Компрессор') = lower('компрессор')")
        )).scalar() == 1


@pytest.mark.asyncio
async def test_item_case_insensitive_upsert(temp_db):
    """Регрессия: смена регистра не должна плодить дубли предметов."""
    ctx, engine, crud = temp_db

    async with ctx() as s:
        await crud.upsert_item_location(s, UID, "Компрессор", "стеллаж")
    async with ctx() as s:
        await crud.upsert_item_location(s, UID, "компрессор", "верстак")

    async with ctx() as s:
        items = await crud.list_all_items(s, user_id=UID)
    assert len(items) == 1
    assert items[0].location == "верстак"
    # Название сохраняется в том виде, как его произнёс пользователь
    assert items[0].item_name == "компрессор"


# --- Ранжирование поиска вещей ---

def test_search_scoring_prefers_best_match():
    from bot.database.crud import _token_overlap_score

    inventory = [
        "Домкрат гидравлический",
        "Домкрат ромбический",
        "Ключ на 13",
        "Съёмник подшипников",
        "Набор ключей гаечных",
    ]

    def top(query):
        scored = [(i, _token_overlap_score(query, i)) for i in inventory]
        scored = [(n, s) for n, s in scored if s > 0]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[0][0] if scored else None

    assert "Домкрат" in top("домкрат")
    assert top("подшипник") == "Съёмник подшипников"
    assert top("подшипников") == "Съёмник подшипников"  # склонение
    assert top("компрессор") is None
    assert top("абракадабра") is None
    assert "Ключ" in top("где лежит ключ на 13")
    assert top("набор ключей") == "Набор ключей гаечных"


def test_search_scoring_exact_beats_partial():
    from bot.database.crud import _token_overlap_score

    exact = _token_overlap_score("Домкрат", "Домкрат")
    partial = _token_overlap_score("Домкрат", "Домкрат ромбический 2 тонны")
    assert exact > partial


def test_search_scoring_returns_zero_for_empty():
    from bot.database.crud import _token_overlap_score
    assert _token_overlap_score("", "Домкрат") == 0
    assert _token_overlap_score("Домкрат", "") == 0
    assert _token_overlap_score("где", "Домкрат") == 0  # только стоп-слово


# --- История диалога ---

@pytest.mark.asyncio
async def test_chat_history_order_and_prune(temp_db):
    ctx, engine, crud = temp_db

    for i in range(5):
        async with ctx() as s:
            await crud.add_chat_message(s, UID, "user" if i % 2 == 0 else "assistant", f"msg {i}")

    async with ctx() as s:
        history = await crud.get_recent_chat_history(s, user_id=UID, limit=3)
    # Хронологический порядок: от старых к новым
    assert [h["content"] for h in history] == ["msg 2", "msg 3", "msg 4"]

    async with ctx() as s:
        removed = await crud.prune_chat_history(s, user_id=UID, keep_last=2)
    assert removed == 3


# --- Разбор карточки из текста ---

def test_parse_card_text_handles_real_html():
    """Парсер должен понимать HTML, который реально отправляет бот."""
    from bot.handlers.callback_handler import parse_card_text

    fuel_html = (
        "⛽ <b>Заправка</b>\n"
        "• <b>Литры:</b> <code>42.5 л</code>\n"
        "• <b>Сумма:</b> <code>2 500 ₽</code>\n"
        "• <b>Цена за литр:</b> <code>58.82 ₽</code>\n"
        "• <b>Пробег:</b> <code>154 300 км</code>\n"
        "• <b>АЗС:</b> <i>Лукойл</i>"
    )
    intent, data = parse_card_text(fuel_html)
    assert intent == "fuel"
    assert data["liters"] == 42.5
    assert data["cost"] == 2500.0
    assert data["odometer"] == 154300
    assert data["station"] == "Лукойл"
    # В базу не должно утечь HTML
    assert "<" not in str(data)


def test_parse_card_text_task():
    from bot.handlers.callback_handler import parse_card_text

    html = (
        "📝 <b>Новая задача</b>\n"
        "• <b>Дело:</b> <b>купить грабли</b>\n"
        "• <b>Срок:</b> <code>завтра</code>"
    )
    intent, data = parse_card_text(html)
    assert intent == "task_save"
    assert data["title"] == "купить грабли"
    assert data["due_date"] == "завтра"


def test_parse_card_text_handles_placeholders():
    from bot.handlers.callback_handler import parse_card_text

    html = "⛽ <b>Заправка</b>\n• <b>Литры:</b> <code>не указано</code>\n• <b>Сумма:</b> <code>не указана</code>"
    intent, data = parse_card_text(html)
    assert intent == "fuel"
    assert data["liters"] is None
    assert data["cost"] is None


def test_parse_card_text_ignores_garbage():
    from bot.handlers.callback_handler import parse_card_text
    assert parse_card_text("просто текст без карточки") == (None, {})


# --- Клавиатуры: все callback_data валидны ---

def test_all_keyboard_callbacks_fit_and_are_unique():
    """Telegram ограничивает callback_data 64 байтами — проверяем все кнопки."""
    from bot.keyboards.inline import (
        get_edit_field_keyboard,
        get_entry_confirm_keyboard,
        get_main_menu_keyboard,
        get_tasks_keyboard,
        get_undo_task_keyboard,
    )

    class FakeTask:
        def __init__(self, i, title):
            self.id = i
            self.title = title

    keyboards = [
        get_main_menu_keyboard(),
        get_entry_confirm_keyboard("abc12345"),
        get_edit_field_keyboard("fuel", "abc12345"),
        get_tasks_keyboard([FakeTask(i, "Очень длинное название задачи " * 5) for i in range(1, 12)]),
        get_undo_task_keyboard(999999),
    ]

    for kb in keyboards:
        assert kb is not None
        for row in kb.inline_keyboard:
            for btn in row:
                encoded = btn.callback_data.encode()
                assert len(encoded) <= 64, f"callback_data слишком длинный ({len(encoded)}): {btn.callback_data}"
                assert btn.text and len(btn.text) <= 64, f"текст кнопки слишком длинный: {btn.text}"


def test_tasks_keyboard_respects_button_cap():
    from bot.keyboards.inline import MAX_TASK_BUTTONS, get_tasks_keyboard

    class FakeTask:
        def __init__(self, i):
            self.id = i
            self.title = f"задача {i}"

    kb = get_tasks_keyboard([FakeTask(i) for i in range(1, 30)])
    # Не больше MAX_TASK_BUTTONS кнопок задач + одна на «всё выполнено»
    assert len(kb.inline_keyboard) == MAX_TASK_BUTTONS + 1


# --- Форматтеры чисел ---

def test_number_formatting_uses_spaces_not_commas():
    from bot.services.formatters import fmt_int, fmt_km, fmt_liters, fmt_money

    assert fmt_int(154300) == "154 300"
    assert fmt_int(1234567) == "1 234 567"
    assert fmt_km(150000) == "150 000 км"
    assert fmt_money(2500) == "2 500 ₽"
    assert fmt_money(58.82, 2) == "58.82 ₽"
    assert fmt_liters(42.55) == "42.5 л"
    # Мусор не должен ронять форматирование
    assert fmt_int(None) == "—"
    assert fmt_money("abc") == "—"


def test_confirmed_text_has_no_raw_html_tags():
    from bot.services.formatters import format_confirmed

    text = format_confirmed("fuel", {"liters": 42.5, "cost": 2500}, consumption=9.4)
    assert "9.4" in text
    assert "2 500" in text
    # Никаких неэкранированных спецсимволов, которые сломали бы Telegram HTML
    assert "<code>" in text and "</code>" in text


# --- Даты ---

def test_parse_due_relative_and_absolute():
    from bot.services.dates import parse_due

    now = datetime(2026, 9, 30, 14, 30)  # среда
    assert parse_due("завтра", now) == datetime(2026, 10, 1, 9, 0)
    assert parse_due("сегодня вечером", now) == datetime(2026, 9, 30, 19, 0)
    assert parse_due("через 3 дня", now) == datetime(2026, 10, 3, 9, 0)
    assert parse_due("в субботу", now) == datetime(2026, 10, 3, 9, 0)
    assert parse_due("25.12", now) == datetime(2026, 12, 25, 9, 0)
    assert parse_due("2026-10-05T19:00:00", now) == datetime(2026, 10, 5, 19, 0)


def test_parse_due_does_not_mistake_dates_for_times():
    """Регрессия: «14.10» раньше читалось как время «14:10»."""
    from bot.services.dates import parse_due

    now = datetime(2026, 9, 30, 14, 30)
    assert parse_due("14.10", now) == datetime(2026, 10, 14, 9, 0)
    assert parse_due("25.12", now) == datetime(2026, 12, 25, 9, 0)
    # Явное время суток, наоборот, должно читаться как время
    assert parse_due("в 18:30", now) == datetime(2026, 9, 30, 18, 30)


def test_parse_due_rejects_nonsense():
    from bot.services.dates import parse_due

    now = datetime(2026, 9, 30, 14, 30)
    assert parse_due("бред", now) is None
    assert parse_due("", now) is None
    assert parse_due(None, now) is None
    # Просроченная дата не должна возвращаться
    assert parse_due("2020-01-01", now) is None


# --- Токен-бюджет истории ---

def test_token_budget_keeps_last_message_intact():
    from bot.services.llm import build_token_budget

    messages = [{"role": "system", "content": "S" * 100}]
    messages += [{"role": "user", "content": "old " * 50} for _ in range(5)]
    messages.append({"role": "user", "content": "новый вопрос"})

    trimmed = build_token_budget(messages, max_chars=400)

    assert trimmed[-1]["content"] == "новый вопрос"  # последнее не режется
    assert len(trimmed) < len(messages)
    # Системное сообщение и самые старые реплики ушли
    assert trimmed[0]["content"] != "S" * 100


def test_token_budget_returns_single_message_when_huge():
    from bot.services.llm import build_token_budget

    messages = [{"role": "user", "content": "x" * 50000}]
    assert build_token_budget(messages, max_chars=100) == [messages[0]]


# --- Модельная цепочка ---

def test_model_chain_has_no_duplicates():
    from bot.services.llm import model_chain

    chain = model_chain("openai/gpt-oss-120b")
    assert len(chain) == len(set(chain))
    assert chain[0] == "openai/gpt-oss-120b"
    assert len(chain) >= 3  # есть запасные модели


def test_max_tokens_capped_for_short_context_models():
    from bot.services.llm import max_tokens_for

    assert max_tokens_for("openai/gpt-oss-120b", 2000) == 2000
    assert max_tokens_for("qwen/qwen3.8-27b", 2000) <= 800


# --- Черновики карточек ---

def test_draft_store_lifecycle():
    from bot.services import draft_store

    draft_id = draft_store.save_draft(user_id=1, intent="fuel", data={"liters": 40})
    draft = draft_store.get_draft(draft_id)
    assert draft["intent"] == "fuel"

    assert draft_store.update_draft(draft_id, {"liters": 45}) is True
    assert draft_store.get_draft(draft_id)["data"]["liters"] == 45

    assert draft_store.pop_draft(draft_id) is not None
    assert draft_store.get_draft(draft_id) is None


def test_draft_store_rejects_unknown_id():
    from bot.services import draft_store
    assert draft_store.get_draft("nope") is None
    assert draft_store.update_draft("nope", {"a": 1}) is False