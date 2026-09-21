import logging
from typing import Optional, Dict, Any
from openai import AsyncOpenAI

from bot.config import settings
from .base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

TECH_EXPERT_PROMPT = """Ты — субагент технической экспертизы и главный инженер/автомеханик.
Твоя задача — предоставить строгий технический регламент:
1. Необходимый специнструмент и расходники (съемники, головки, динамометрический ключ, смазки, фиксаторы резьбы).
2. Пошаговая технология и регламент работ (что снимать в первую очередь, важные нюансы).
3. Критические моменты безопасности и типичные ошибки новичков (сорванная резьба, перекос, завоздушивание, моменты затяжки).
4. Оценка сложности и примерного времени работ в условиях гаража/сервиса.

ФОРМАТИРОВАНИЕ:
- Только практическая конкретика без «воды».
- Выделяй важные моменты и предостережения жирным (**Внимание**, **Важно**).
- Для формул и расчетов используй Unicode символы (², ³, °, ·, ±).
"""


class TechExpertAgent(BaseAgent):
    """Субагент технической экспертизы, регламентов ремонта и автомеханики."""

    def __init__(self):
        super().__init__(
            name="TechExpert",
            emoji="🔧",
            description="Техническая экспертиза, порядок разборки/сборки, подбор инструментов, моменты затяжки и техника безопасности."
        )

    async def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        logger.info(f"[{self.name}] Запуск субагента для задачи: «{task[:80]}»")
        context = context or {}

        extra_info = context.get("extra_info", "")
        client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.GROQ_API_KEY)

        user_content = f"Техническая задача: {task}"
        if extra_info:
            user_content += f"\nДополнительные вводные:\n{extra_info}"

        try:
            resp = await client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": TECH_EXPERT_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3,
                max_tokens=1400
            )
            summary = resp.choices[0].message.content or "Не удалось сформировать техническое заключение."
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка технического анализа: {e}")
            summary = f"Ошибка технического анализа: {e}"

        return AgentResult(
            agent_name=self.name,
            emoji=self.emoji,
            title="Технический регламент и инструкция мастера",
            summary=summary.strip()
        )
