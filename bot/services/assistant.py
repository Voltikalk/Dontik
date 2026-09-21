import logging
from typing import Optional
from openai import AsyncOpenAI

from bot.config import settings
from bot.services.web_search import search_web

logger = logging.getLogger(__name__)

ASSISTANT_SYSTEM_PROMPT = """Ты — универсальный персональный помощник и эксперт на все случаи жизни (по автомобилям, гаражу, даче, ремонту, бытовым делам, технике, кулинарии и общим вопросам).
Тебя зовут Пётр.
Твоя цель — давать максимально полезные, четкие, точные и дружелюбные ответы на русском языке.

Правила ответов:
1. Отвечай кратко, по делу и структурировано (используй списки и выделение важного, где уместно).
2. Избегай лишней воды, длинных предисловий и шаблонных фраз.
3. Если предоставлены результаты поиска в интернете — опирайся на них как на источник свежих и актуальных фактов (курсы валют, погода, цены, новости, характеристики).
4. Если результаты поиска пустые или не требуются — используй свои обширные знания.
5. Форматируй ответ в аккуратном виде, подходящем для чтения в Telegram (можно использовать HTML или читаемый текст без битых тегов).
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
    search_query: Optional[str] = None
) -> str:
    """
    Генерирует ответ ассистента на произвольный вопрос пользователя.
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

    # Формирование сообщений для модели
    prompt_content = f"Вопрос пользователя: {user_query}"
    if web_context:
        prompt_content += (
            f"\n\n{web_context}\n"
            "Используй приведенные выше данные из интернета, чтобы дать актуальный и точный ответ на вопрос пользователя."
        )

    client = get_groq_client()
    candidate_models = [settings.GROQ_MODEL]
    for fallback in ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "groq/compound-mini"]:
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    for model_name in candidate_models:
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": ASSISTANT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_content}
                ],
                temperature=0.4,
                max_tokens=1024
            )
            content = response.choices[0].message.content or ""
            if content.strip():
                return content.strip()
        except Exception as e:
            logger.warning(f"Модель {model_name} вернула ошибку при ответе ассистента: {e}")
            continue

    return "Прости, не удалось получить ответ от нейросети прямо сейчас. Попробуй задать вопрос чуть позже."
