import logging
from typing import Optional, Dict, Any, List
from openai import AsyncOpenAI

from bot.config import settings
from bot.services.web_search import search_web
from .base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

SEARCH_AGENT_PROMPT = """Ты — субагент глубокого поиска и рыночной аналитики.
Твоя задача — извлечь из результатов веб-поиска актуальные факты:
- Цены, диапазоны стоимости, расценки на услуги и запчасти
- Артикулы, номера деталей (OEM / аналоги), надежные бренды
- Источники, платформы (Авито, Exist, Автодок, Яндекс.Маркет, профильные магазины)
- Сравнение вариантов (плюсы, минусы, предостережения о подделках)

ПРАВИЛА:
1. Пиши кратко, емко, структурированно (списками).
2. Выделяй цифры, цены и артикулы жирным (**жирный текст**).
3. Не лей воду, переходи сразу к конкретике.
"""


class SearchAnalystAgent(BaseAgent):
    """Субагент глубокого поиска в интернете, сбора цен и аналитики рынка."""

    def __init__(self):
        super().__init__(
            name="SearchAnalyst",
            emoji="🔍",
            description="Глубокий поиск в интернете, проверка цен на запчасти, поиск артикулов и поставщиков."
        )

    async def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        logger.info(f"[{self.name}] Запуск субагента для задачи: «{task[:80]}»")
        context = context or {}

        # 1. Формируем поисковый запрос (или используем переданный)
        search_q = context.get("search_query") or task
        # Чистим запрос от лишних слов
        search_q = search_q.replace("пожалуйста", "").replace("найди", "").strip()

        # 2. Выполняем веб-поиск
        results = await search_web(search_q, max_results=5)
        sources = []
        snippets = []

        if results:
            for idx, r in enumerate(results, 1):
                snippets.append(f"[{idx}] {r['title']}\n{r['body']}\nИсточник: {r['href']}")
                if r.get("href"):
                    sources.append(r["href"])

        search_text = "\n\n".join(snippets) if snippets else "По прямому запросу данных в поисковике не найдено."

        # 3. Анализируем через LLM
        from .llm_helper import call_subagent_llm
        user_prompt = (
            f"Задача пользователя: {task}\n\n"
            f"--- НАЙДЕННЫЕ МАТЕРИАЛЫ В СЕТИ ---\n{search_text}\n-----------------------------------\n"
            "Подготовь четкую аналитическую сводку по ценам, артикулам, поставщикам и вариантам."
        )

        summary = await call_subagent_llm(
            system_prompt=SEARCH_AGENT_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=750
        )

        return AgentResult(
            agent_name=self.name,
            emoji=self.emoji,
            title="Рыночный поиск и аналитика цен",
            summary=summary.strip(),
            sources=sources[:4],
            metadata={"found_sources": len(sources)}
        )
