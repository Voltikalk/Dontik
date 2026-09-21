import logging
from typing import Optional, Dict, Any
from openai import AsyncOpenAI

from bot.config import settings
from .base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

PLANNER_AGENT_PROMPT = """Ты — субагент стратегического планирования и управления проектами.
Твоя задача — составить четкий, поэтапный план реализации задачи:
1. Подготовительный этап (закупка, подготовка места, проверка инструмента).
2. Основной этап (хронологический порядок шагов с оценкой времени на каждый шаг).
3. Финальный этап (проверка качества, контрольные испытания, уборка).
4. Чек-лист готовности к началу работ.

ФОРМАТИРОВАНИЕ:
- Используй нумерованные этапы и маркеры [ ] для задач.
- Указывай ориентировочное время на каждый этап (например: Этап 1 [~40 мин]).
- Кратко, четко, без лишних вступлений.
"""


class PlannerAgent(BaseAgent):
    """Субагент планирования, дорожных карт и пошаговых чек-листов."""

    def __init__(self):
        super().__init__(
            name="Planner",
            emoji="📋",
            description="Составление пошаговых дорожных карт, чек-листов, временных оценок и этапов проекта."
        )

    async def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        logger.info(f"[{self.name}] Запуск субагента для задачи: «{task[:80]}»")
        context = context or {}

        tech_summary = context.get("tech_summary", "")
        client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.GROQ_API_KEY)

        user_content = f"Цель проекта / план: {task}"
        if tech_summary:
            user_content += f"\n\n--- ТЕХНИЧЕСКИЙ РЕГЛАМЕНТ ---\n{tech_summary[:2000]}"

        try:
            resp = await client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": PLANNER_AGENT_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3,
                max_tokens=1200
            )
            summary = resp.choices[0].message.content or "Не удалось сформировать план."
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка планирования: {e}")
            summary = f"Ошибка планирования: {e}"

        return AgentResult(
            agent_name=self.name,
            emoji=self.emoji,
            title="Пошаговый план и чек-лист проекта",
            summary=summary.strip()
        )
