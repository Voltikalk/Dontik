import logging
from typing import Optional, List, Dict
from openai import AsyncOpenAI

from bot.config import settings
from bot.services.web_search import search_web

logger = logging.getLogger(__name__)

ASSISTANT_SYSTEM_PROMPT = """Ты — универсальный персональный помощник и эксперт на все случаи жизни (по автомобилям, гаражу, даче, ремонту, бытовым делам, технике, точным наукам, математике, физике, кулинарии и общим вопросам).
Тебя зовут Пётр.
Твоя цель — давать максимально полезные, четкие, точные и дружелюбные ответы на русском языке с красивым форматированием для Telegram.

ПРАВИЛА ОФОРМЛЕНИЯ ДЛЯ TELEGRAM:
1. Выделяй важные термины, ключевые мысли и подзаголовки жирным шрифтом (**жирный текст**).
2. Для списков используй понятные маркеры (• или 1, 2, 3).
3. Избегай лишней воды и шаблонных вступлений («Конечно!», «Рад помочь!») — переходи сразу к делу.
4. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:
   - НЕ ПИШИ сырой код LaTeX (никаких \\sqrt, \\frac, \\pm, \\approx, \\cdot, \\in, \\quad, \\left, \\right и т.д.). В Telegram НЕТ поддержки рендеринга LaTeX! Для пользователя это выглядит как непонятный машинный код.
   - НЕ ОБОРАЧИВАЙ математические формулы в блоки кода (```latex или ```). Блоки кода в Telegram предназначены ИСКЛЮЧИТЕЛЬНО для языков программирования (Python, JS, SQL, Bash).
5. ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ И ФОРМУЛ:
   - Все формулы и расчеты пиши красивым человекочитаемым текстом с использованием Unicode-символов:
     • Степени: ⁰, ¹, ², ³, ⁴, ⁵, ⁶, ⁷, ⁸, ⁹, ⁿ, ˣ, ⁻¹, ⁻² (например: x² = 38, 6² = 36, 10⁻⁵)
     • Индексы: ₀, ₁, ₂, ₃, ₄, ₅, ₆, ₇, ₈, ₉ (например: x₁, x₂, a₀, H₂O)
     • Знаки: √ (корень), ± (плюс-минус), ≈ (приблизительно), ≠ (не равно), ≤, ≥, · (умножение), ÷, − (минус)
     • Множества и константы: ∈, ∉, ∅, ∞, π, Δ
     • Дроби: пиши через наклонную черту со скобками, например: (a + b) / 2
   - Выделяй ключевые формулы жирным шрифтом или цитатой:
     > **x = ±√38 ≈ ±6.16**
   - Расписывай решение подробно по шагам:
     • Исходное уравнение
     • Шаг решения
     • Точные корни: **x₁ = √38**, **x₂ = −√38**
     • Приближенные значения: **√38 ≈ 6.16**
     • Итоговый ответ
6. ЕСЛИ ПРЕДОСТАВЛЕНЫ ДАННЫЕ ИЗ ИНТЕРНЕТА:
   - Опирайся на них как на источник свежих фактов (курсы валют, погода, цены, новости).
"""


def get_groq_client() -> AsyncOpenAI:
    """Создает экземпляр AsyncOpenAI клиента для Groq API."""
    return AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=settings.GROQ_API_KEY
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
            "Используй приведенные выше данные из интернета, чтобы дать актуальный и точный ответ на вопрос пользователя."
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
    candidate_models = [settings.GROQ_MODEL]
    for fallback in ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "groq/compound-mini"]:
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    for model_name in candidate_models:
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.4,
                max_tokens=2048
            )
            content = response.choices[0].message.content or ""
            if content.strip():
                return content.strip()
        except Exception as e:
            logger.warning(f"Модель {model_name} вернула ошибку при ответе ассистента: {e}")
            continue

    return "Прости, не удалось получить ответ от нейросети прямо сейчас. Попробуй задать вопрос чуть позже."
