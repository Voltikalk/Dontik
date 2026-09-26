import logging
from typing import Optional, List, Dict
from openai import AsyncOpenAI

from bot.config import settings
from bot.services.web_search import search_web

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

5. ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ И ФОРМУЛ:
   - НЕ ПИШИ сырой код LaTeX (никаких \\sqrt, \\frac, \\pm, \\approx, \\cdot, \\in, \\quad и т.д.).
   - Все формулы и расчеты пиши красивым человекочитаемым текстом с использованием Unicode-символов:
     • Степени: ⁰, ¹, ², ³, ⁴, ⁵, ⁶, ⁷, ⁸, ⁹, ⁿ, ˣ, ⁻¹, ⁻² (например: x² = 38, 6² = 36)
     • Индексы: ₀, ₁, ₂, ₃, ₄, ₅, ₆, ₇, ₈, ₉ (например: x₁, x₂, a₀, H₂O)
     • Знаки: √ (корень), ± (плюс-минус), ≈ (приблизительно), ≠ (не равно), ≤, ≥, · (умножение), ÷, − (минус), π
     • Дроби: пиши через наклонную черту со скобками, например: (a + b) / 2
   - Выделяй ключевые формулы жирным шрифтом или цитатой:
     > **x = ±√38 ≈ ±6.16**
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
    search_sources = []

    if needs_web:
        effective_query = search_query.strip() if search_query else user_query.strip()
        logger.info(f"Выполняется адаптивный веб-поиск для ассистента: «{effective_query}»")
        search_results = await search_web(effective_query, max_results=4)

        if search_results:
            snippets = []
            for idx, r in enumerate(search_results, 1):
                snippets.append(f"[{idx}] {r['title']}\n{r['body']}\nИсточник: {r['href']}")
                if r.get("href"):
                    search_sources.append(r["href"])
            web_context = (
                "\n\n--- АКТУАЛЬНЫЕ ДАННЫЕ ИЗ СЕТИ ИНТЕРНЕТ (DuckDuckGo) ---\n"
                + "\n\n".join(snippets)
                + "\n--------------------------------------------------------\n"
            )

    # Текущий запрос пользователя
    prompt_content = f"Вопрос пользователя: {user_query}"
    if web_context:
        prompt_content += (
            f"\n\n{web_context}\n"
            "СТРОГАЯ ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ РЕЗУЛЬТАТОВ ПОИСКА:\n"
            "1. Не пересказывай поисковую выдачу списком сайтов! Сформируй единый, структурированный, готовый ответ на вопрос пользователя.\n"
            "2. Никаких таблиц с разделителями (|...|)! Оформляй списки компактно и наглядно.\n"
            "3. Если полезно указать источники, добавь в самый конец одну строку: '🔗 **Источники:** [Название](URL) • [Название](URL)'."
        )

    # Формирование сообщений с историей диалога
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
            err_str = str(e)
            logger.warning(f"Модель {model_name} вернула ошибку при ответе ассистента: {e}")

            # Если превышен лимит входных токенов (413 / Request too large / ITPM)
            if any(term in err_str.lower() for term in ["413", "too large", "limit 7000", "itpm"]):
                logger.info("Аварийное сжатие контекста запроса для обхода лимита токенов Groq...")
                short_prompt = prompt_content
                if len(short_prompt) > 3000:
                    short_prompt = short_prompt[:3000] + "\n\n... [данные сокращены по лимиту нейросети]"
                compressed_messages = [
                    {"role": "system", "content": ASSISTANT_SYSTEM_PROMPT},
                    {"role": "user", "content": short_prompt}
                ]
                try:
                    retry_resp = await client.chat.completions.create(
                        model=model_name,
                        messages=compressed_messages,
                        temperature=0.3,
                        max_tokens=700
                    )
                    retry_content = retry_resp.choices[0].message.content or ""
                    if retry_content.strip():
                        return retry_content.strip()
                except Exception as retry_e:
                    logger.warning(f"Повторный сжатый запрос для {model_name} также не удался: {retry_e}")

            continue

    return "Прости, не удалось получить ответ от нейросети прямо сейчас. Попробуй задать вопрос чуть позже."
