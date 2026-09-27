import time
import re
import logging
from typing import Optional, List, Dict, AsyncGenerator
from openai import AsyncOpenAI
from aiogram.types import Message, LinkPreviewOptions
from aiogram.enums import ParseMode

from bot.config import settings
from bot.services.web_search import search_web
from bot.emojis import E_SEARCH, E_THINK, E_ALERT
from bot.services.formatters import md_to_telegram_html, send_formatted_message

logger = logging.getLogger(__name__)

ASSISTANT_SYSTEM_PROMPT = """Ты — универсальный персональный помощник и эксперт на все случаи жизни (по автомобилям, гаражу, даче, ремонту, бытовым делам, технике, точным наукам, математике, физике, кулинарии, истории и общим вопросам).
Тебя зовут Пётр.
Твоя цель — давать максимально полезные, четкие, точные, лаконичные и структурированные ответы на русском языке с безупречным визуальным оформлением для Telegram.

СТРОГИЕ ПРАВИЛА ОФОРМЛЕНИЯ И СТРУКТУРЫ ДЛЯ TELEGRAM:
1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНЫ MARKDOWN-ТАБЛИЦЫ (| колонка | колонка |):
   - В мобильном Telegram таблицы НЕ поддерживаются и превращаются в кашу, уродуя текст на экранах!
   - Любые сравнительные данные, списки параметров, характеристики или хронологии оформляй ИСКЛЮЧИТЕЛЬНО компактными списками.

2. НИКАКОЙ ВОДЫ И ШАБЛОННЫХ ФРАЗ:
   - ЗАПРЕЩЕНЫ вводные предисловия («Конечно!», «Рад помочь!», «Ниже собраны проверенные источники...», «Вот подробная информация...»). Сразу переходи к сути вопроса!
   - ЗАПРЕЩЕНЫ шаблонные концовки («Если возникнут вопросы, обращайтесь!», «Для полного изучения откройте указанные ресурсы...», «Дай знать, если нужен другой формат»).

3. КОМПАКТНОСТЬ, СТРУКТУРА И ЧИТАБЕЛЬНОСТЬ СПИСКОВ:
   - Дели объемную информацию на логические смысловые блоки с четкими краткими подзаголовками (**Жирный заголовок**).
   - Для списков, этапов, хронологий и родословных используй компактный однострочный формат:
     • **Имя / Название** (период, ключевая дата или параметр) — краткая суть или главное достижение в одно предложение.
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО раздувать один элемент на 4-5 отдельных строк с повторением ярлыков («Правитель: ...», «Годы жизни: ...», «Примечание: ...»)! Это засоряет экран и делает текст нечитабельным.
   - Для родословных и иерархий показывай преемственность наглядно через ветви или стрелки:
     • **Михаил Фёдорович** (1613–1645) — основатель династии
       ↳ Сын: **Алексей Михайлович** (1645–1676)
   - ЗАПРЕЩЕНЫ ленивые троеточия (вроде «• …»). Если перечисляешь ключевых правителей или этапы — перечисли их связно или дай законченную схему основных вех.

4. ПРАВИЛА РАБОТЫ С ВЕБ-ПОИСКОМ (СИНТЕЗ, А НЕ ПЕРЕСКАЗ ВЫДАЧИ):
   - Если предоставлены данные из интернета — извлеки факты и синтезируй единый, готовый ответ.
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО копировать или пересказывать результаты поиска в виде списка сайтов («1️⃣ Википедия 🔗 https://... 2️⃣ ...»)! Пользователь спрашивает не о том, что нашел поисковик, а ждет готовый ответ по существу.
   - ЗАПРЕЩЕНО вставлять длинные голые URL в текст сообщений. Если уместно дать источники (для интерактивных схем или проверки данных), укажи их в самом конце одной компактной строкой через Markdown-ссылки:
     🔗 **Источники:** [Википедия](URL) • [Название](URL)

5. ПРАВИЛА ВЫВОДА МАТЕМАТИКИ (Rich Messages с нативным KaTeX рендерингом):
   - Telegram Bot API 10.1+ нативно рендерит математику через KaTeX!
   - Inline-формулы (внутри строк) ВСЕГДА оборачивай в <tg-math>...</tg-math>.
     Пример: где <tg-math>G \\approx 0.9159</tg-math> — каталогово число.
     Пример: Работает при <tg-math>\\text{Re}(s) > 1</tg-math>.
   - Выключные формулы (на отдельной строке) ВСЕГДА оборачивай в <tg-math-block>...</tg-math-block>.
     Пример:
     <tg-math-block>\\int_0^1 x^{-x} dx = \\sum_{n=1}^\\infty \\frac{1}{n^n} \\approx 1.2913</tg-math-block>
     Пример:
     <tg-math-block>\\int_0^{\\pi/4} \\ln(\\tan x) dx = -G</tg-math-block>
   - Внутри тегов пиши чистый LaTeX без делимитров $...$, $$...$, \\(...\\), \\[...\\].
   - Используй стандартные LaTeX-команды: \\int, \\sum, \\frac, \\pi, \\infty, \\zeta, \\sqrt, \\sin, \\cos, \\ln, \\Gamma, \\approx.
   - Дроби в степенях всегда заключай в фигурные скобки: x^{s-1}, e^{-x^2}, e^{-b^2}, x^{3/2}.
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО заменять LaTeX на псевдо-символы Unicode (∫, ∑, ², ³) внутри формул — пиши чистый LaTeX (\\int, \\sum, ^2, ^3).
   - Вне математики используй обычный текст или HTML-теги: <b>, <i>, <code>, <blockquote>.
   - Не оборачивай формулы в <code> или <pre> — для математики есть специальные теги <tg-math> и <tg-math-block>.
   - ИТОГОВЫЙ ответ или главную формулу при пошаговом решении выделяй через \\boxed{...}:
     <tg-math-block>\\boxed{I = \\frac{\\pi^4}{15}}</tg-math-block>
"""


def get_groq_client() -> AsyncOpenAI:
    """Создает экземпляр AsyncOpenAI клиента для Groq API без блокирующих ретраев."""
    return AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=settings.GROQ_API_KEY,
        max_retries=0
    )


async def answer_query(
    user_query: str,
    needs_web: bool = False,
    search_query: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Генерирует ответ ассистента на произвольный вопрос пользователя.
    Поддерживает контекст предыдущих реплик диалога (history).
    При необходимости выполняет веб-поиск через DuckDuckGo и передает результаты в LLM.
    """
    web_context = ""
    if needs_web:
        effective_query = search_query.strip() if search_query else user_query.strip()
        logger.info(f"Выполняется адаптивный веб-поиск для ассистента: «{effective_query}»")
        search_results = await search_web(effective_query, max_results=4)

        if search_results:
            snippets = []
            for idx, r in enumerate(search_results, 1):
                snippets.append(f"[{idx}] {r['title']}\n{r['body']}\nИсточник: {r['href']}")
            web_context = (
                "\n\n--- АКТУАЛЬНЫЕ ДАННЫЕ ИЗ СЕТИ ИНТЕРНЕТ (DuckDuckGo) ---\n"
                + "\n\n".join(snippets)
                + "\n--------------------------------------------------------\n"
            )

    prompt_content = f"Вопрос пользователя: {user_query}"
    if web_context:
        prompt_content += (
            f"\n\n{web_context}\n"
            "СТРОГАЯ ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ РЕЗУЛЬТАТОВ ПОИСКА:\n"
            "1. Не пересказывай поисковую выдачу списком сайтов! Сформируй единый, структурированный, готовый ответ на вопрос пользователя.\n"
            "2. Никаких таблиц с разделителями (|...|)! Оформляй списки компактно и наглядно.\n"
            "3. Если полезно указать источники, добавь в самый конец одну строку: '🔗 **Источники:** [Название](URL) • [Название](URL)'."
        )

    messages = [{"role": "system", "content": ASSISTANT_SYSTEM_PROMPT}]
    if history:
        for item in history:
            role = item.get("role")
            content = item.get("content", "").strip()
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": prompt_content})

    client = get_groq_client()
    candidate_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]

    for model_name in candidate_models:
        try:
            req_tokens = 750 if "qwen" in model_name else 1400
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=req_tokens
            )
            content = response.choices[0].message.content or ""
            if content.strip():
                return content.strip()
        except Exception as e:
            logger.warning(f"Модель {model_name} вернула ошибку при ответе ассистента: {e}")
            continue

    return "Прости, не удалось получить ответ от нейросети прямо сейчас. Попробуй задать вопрос чуть позже."


async def stream_query_answer(
    user_query: str,
    needs_web: bool = False,
    search_query: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None
) -> AsyncGenerator[str, None]:
    """
    Генерирует потоковый ответ ассистента по токенам (stream=True).
    Поддерживает контекст предыдущих реплик диалога и результаты веб-поиска.
    """
    web_context = ""
    if needs_web:
        effective_query = search_query.strip() if search_query else user_query.strip()
        logger.info(f"Выполняется адаптивный веб-поиск для ассистента: «{effective_query}»")
        search_results = await search_web(effective_query, max_results=4)

        if search_results:
            snippets = []
            for idx, r in enumerate(search_results, 1):
                snippets.append(f"[{idx}] {r['title']}\n{r['body']}\nИсточник: {r['href']}")
            web_context = (
                "\n\n--- АКТУАЛЬНЫЕ ДАННЫЕ ИЗ СЕТИ ИНТЕРНЕТ (DuckDuckGo) ---\n"
                + "\n\n".join(snippets)
                + "\n--------------------------------------------------------\n"
            )

    prompt_content = f"Вопрос пользователя: {user_query}"
    if web_context:
        prompt_content += (
            f"\n\n{web_context}\n"
            "СТРОГАЯ ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ РЕЗУЛЬТАТОВ ПОИСКА:\n"
            "1. Не пересказывай поисковую выдачу списком сайтов! Сформируй единый, структурированный, готовый ответ на вопрос пользователя.\n"
            "2. Никаких таблиц с разделителями (|...|)! Оформляй списки компактно и наглядно.\n"
            "3. Если полезно указать источники, добавь в самый конец одну строку: '🔗 **Источники:** [Название](URL) • [Название](URL)'."
        )

    messages = [{"role": "system", "content": ASSISTANT_SYSTEM_PROMPT}]
    if history:
        for item in history:
            role = item.get("role")
            content = item.get("content", "").strip()
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": prompt_content})

    client = get_groq_client()
    candidate_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]

    for model_name in candidate_models:
        try:
            req_tokens = 750 if "qwen" in model_name else 1400
            stream_resp = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=req_tokens,
                stream=True
            )
            has_yielded = False
            async for chunk in stream_resp:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    has_yielded = True
                    yield delta
            if has_yielded:
                return
        except Exception as e:
            logger.warning(f"Ошибка потоковой генерации {model_name}: {e}")
            continue

    # Резервный вызов, если стриминг не удался
    fallback_full = await answer_query(
        user_query=user_query,
        needs_web=needs_web,
        search_query=search_query,
        history=history
    )
    yield fallback_full


async def stream_assistant_response(
    message: Message,
    user_query: str,
    needs_web: bool = False,
    search_query: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    status_msg: Optional[Message] = None
) -> str:
    """
    Осуществляет плавный потоковый вывод ответа ассистента в Telegram в реальном времени.
    - Обновляет сообщение каждые 0.5-0.7 секунды с эффектом живого набора текста (курсор ▌).
    - Защищен от превышения лимитов Telegram (Flood control) и синтаксических ошибок неполных HTML тегов.
    - По завершении генерации отправляет законченное сообщение: с нативным KaTeX рендерингом для формул
      (через Rich Messages API) или обновляет текущее сообщение.
    - Возвращает полный итоговый текст ответа для сохранения в историю диалога.
    """
    if status_msg is None:
        wait_text = (
            f"{E_SEARCH} <i>Ищу актуальную информацию в интернете...</i>"
            if needs_web
            else f"{E_THINK} <i>Думаю над ответом...</i>"
        )
        status_msg = await message.answer(wait_text)

    full_text = ""
    last_edit_time = time.time()
    last_edited_text = ""

    async for delta in stream_query_answer(
        user_query=user_query,
        needs_web=needs_web,
        search_query=search_query,
        history=history
    ):
        full_text += delta
        now = time.time()
        # Троттлинг обновлений: не чаще 1 раза в 0.6 сек и если накопилось >= 12 новых символов
        if (now - last_edit_time >= 0.6) and (len(full_text) - len(last_edited_text) >= 12):
            preview = re.sub(r'</?(?:tg-math|tg-math-block|b|i|u|s|code|pre|blockquote)[^>]*?>?', '', full_text).strip()
            if preview:
                try:
                    await status_msg.edit_text((preview + " ▌")[:4000], parse_mode=None)
                    last_edit_time = now
                    last_edited_text = full_text
                except Exception:
                    pass

    # Финализация: когда ответ полностью получен
    if not full_text.strip():
        full_text = await answer_query(
            user_query=user_query,
            needs_web=needs_web,
            search_query=search_query,
            history=history
        )

    final_html = md_to_telegram_html(full_text)
    has_rich_math = bool(re.search(r'</?(?:tg-math|tg-math-block)\b', final_html, re.IGNORECASE))
    is_long = len(full_text) > 3800

    if has_rich_math or is_long:
        # Для формул KaTeX (Rich Messages) или длинных разбитых сообщений
        try:
            await status_msg.delete()
        except Exception:
            pass
        await send_formatted_message(message, full_text)
    else:
        # Для обычных сообщений обновляем текущий пузырь без лишних удалений
        try:
            await status_msg.edit_text(
                final_html,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        except Exception:
            try:
                await status_msg.delete()
            except Exception:
                pass
            await send_formatted_message(message, full_text)

    return full_text
