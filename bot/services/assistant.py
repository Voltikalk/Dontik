import time
import re
import asyncio
import logging
from typing import Optional, List, Dict, AsyncGenerator
from openai import AsyncOpenAI
from aiogram.types import Message, LinkPreviewOptions
from aiogram.enums import ParseMode

from bot.config import settings
from bot.services.web_search import search_web
from bot.emojis import E_SEARCH, E_THINK, E_ALERT
from bot.services.formatters import (
    md_to_telegram_html,
    send_formatted_message,
    convert_rich_tags_to_unicode,
    fix_squished_bullets
)
from bot.services.rich_message import send_rich_response, send_rich_draft_update

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

3. СТРОГИЕ ПРАВИЛА ОФОРМЛЕНИЯ СПИСКОВ:
   - Каждый пункт списка ОБЯЗАТЕЛЬНО должен начинаться с НОВОЙ СТРОКИ:
     • **Имя / Название** (период, дата или параметр) — краткая суть или главное достижение в одно предложение.
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО объединять несколько пунктов списка в одну строку через точку « • »! Каждый пункт — строго отдельная строка с отступом.
   - Заголовок блока ВСЕГДА отделяй от списка переводом строки:
     **Интегралы для практики:**
     • Пункт 1
     • Пункт 2
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

5. ПРАВИЛА ВЫВОДА МАТЕМАТИКИ И ФОРМУЛ:
   - Все формулы и математические выражения ОБЯЗАТЕЛЬНО пиши в стандартном LaTeX.
   - Блочные формулы (отдельной строкой, ключевые уравнения, выкладки, итоговые формулы) строго выделяй в $$...$$ (или \\[...\\]).
   - Короткие математические символы и формулы внутри строки пиши в $...$.
   - Весь остальной текст оформляй в стандартном Markdown (жирный **...**, курсив *...*, заголовки #, аккуратные списки).
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать экзотические LaTeX-окружения, которые KaTeX не поддерживает. Используй надежные стандартные: aligned, matrix, pmatrix, bmatrix, cases, \\frac{...}{...}, \\sqrt{...}, \\int, \\sum, \\prod, \\lim, \\boxed{...}.
   - Каждый пункт со сложной формулой пиши строго с новой строки:
     • $$\\int x e^{x^2} dx = \\frac{1}{2} e^{x^2} + C$$ — подстановка $u = x^2$
     • $$\\int \\frac{\\sin x}{x} dx = \\text{Si}(x) + C$$ — интегральный синус
     • $$\\int \\frac{dx}{(x^2+1)^2} = \\frac{x}{2(x^2+1)} + \\frac{1}{2} \\text{arctg}\\,x + C$$
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
    candidate_models = [settings.GROQ_MODEL]
    for m in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
        if m not in candidate_models:
            candidate_models.append(m)

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
    candidate_models = [settings.GROQ_MODEL]
    for m in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
        if m not in candidate_models:
            candidate_models.append(m)

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


def clean_for_preview(text: str) -> str:
    """Очищает промежуточный текст для аккуратного отображения курсора при живом наборе."""
    s = fix_squished_bullets(text)
    s = re.sub(r'</?(?:tg-math|tg-math-block)[^>]*?>?', '', s)
    s = re.sub(r'</?(?:b|i|u|s|code|pre|blockquote|a|tg-emoji)[^>]*?>?', '', s)
    s = s.replace(r'\int', '∫').replace(r'\sum', '∑').replace(r'\infty', '∞')
    s = re.sub(r'\\(?:sin|cos|tan|ln|log|exp|sqrt|pi)\b', lambda m: m.group(0)[1:], s)
    s = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'\1/\2', s)
    s = s.replace('$$', ' ').replace('$', '')
    s = re.sub(r'[{}]', '', s)
    return s.strip()


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
    - Обновляет сообщение каждые 0.35-0.5 секунды с эффектом живого набора текста (курсор ▌).
    - При быстром получении ответа обеспечивает визуальную плавность появления.
    - Редактирует сообщение НА МЕСТЕ без лишних удалений и мигания в красивый, валидный Telegram HTML.
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
    last_edit_time = 0.0
    last_edited_len = 0
    edit_count = 0

    async for delta in stream_query_answer(
        user_query=user_query,
        needs_web=needs_web,
        search_query=search_query,
        history=history
    ):
        full_text += delta
        now = time.time()
        # Первый апдейт делаем как только накопилось >= 15 символов!
        # Последующие — каждые 0.35 сек, если добавилось >= 20 символов
        min_interval = 0.35
        min_chars = 15 if last_edited_len == 0 else 20

        if (now - last_edit_time >= min_interval) and (len(full_text) - last_edited_len >= min_chars):
            preview = clean_for_preview(full_text)
            if preview:
                try:
                    await status_msg.edit_text((preview + " ▌")[:4000], parse_mode=None)
                    last_edit_time = now
                    last_edited_len = len(full_text)
                    edit_count += 1
                except Exception:
                    pass

    # Резерв, если ничего не вернулось
    if not full_text.strip():
        full_text = await answer_query(
            user_query=user_query,
            needs_web=needs_web,
            search_query=search_query,
            history=history
        )

    # Если генерация завершилась слишком быстро (меньше 2 правок),
    # показываем 1-2 промежуточных шага для красивого эффекта печати
    if edit_count < 2 and len(full_text) > 80:
        preview_full = clean_for_preview(full_text)
        total_len = len(preview_full)
        if total_len > 60:
            step1_end = int(total_len * 0.45)
            step1_text = preview_full[:step1_end].rsplit(' ', 1)[0]
            try:
                await status_msg.edit_text((step1_text + " ▌")[:4000], parse_mode=None)
                await asyncio.sleep(0.25)
            except Exception:
                pass

            step2_end = int(total_len * 0.8)
            step2_text = preview_full[:step2_end].rsplit(' ', 1)[0]
            try:
                await status_msg.edit_text((step2_text + " ▌")[:4000], parse_mode=None)
                await asyncio.sleep(0.25)
            except Exception:
                pass

    await send_rich_response(
        bot=message.bot,
        chat_id=message.chat.id,
        raw_markdown=full_text,
        status_msg=status_msg
    )

    return full_text
