import logging
from typing import Optional, Dict, Any
from openai import AsyncOpenAI

from bot.config import settings
from .base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

CRITIC_PROMPT = """Ты — строгий технический аудитор, аналитик рисков и субагент глубокого мышления («Критик»).
Твоя задача — критически оценить предварительные выводы других субагентов и найти слабые места:

1. НЕОЧЕВИДНЫЕ ПОДВОДНЫЕ КАМНИ И РИСКИ:
   - Что может пойти не так в реальных условиях (закисшие болты, перекос, обрыв проводки, протечки)?
   - Какие ошибки новичков приводят к поломке или повторному ремонту?

2. СКРЫТЫЕ РАСХОДЫ И МЕЛОЧИ (о которых часто забывают):
   - Одноразовый крепеж, прокладки, сальники, очистители, смазки, герметики.
   - Не занижена ли смета? Нужен ли запас бюджета?

3. РЕАЛИСТИЧНОСТЬ И ТРЕБОВАНИЯ К УСЛОВИЯМ:
   - Нужна ли яма / эстакада / подъемник или помощь напарника?
   - Есть ли специфический инструмент, без которого работу не завершить?

4. ВЕРДИКТ И ТОЧЕЧНЫЕ КОРРЕКТИРОВКИ:
   - Четкие рекомендации по исправлению и улучшению плана.

ФОРМАТИРОВАНИЕ:
- Будь критичен, лаконичен и конкретен.
- Выделяй опасности и ключевые риски жирным (**Внимание**, **Критично**).
"""


class CriticAgent(BaseAgent):
    """Субагент глубокого мышления, поиска рисков, фактчекинга и критики решений."""

    def __init__(self):
        super().__init__(
            name="Critic",
            emoji="🧠",
            description="Глубокий анализ рисков, проверка гипотез, поиск скрытых расходов и аудит надежности."
        )

    async def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        logger.info(f"[{self.name}] Запуск критика-аудитора для задачи: «{task[:80]}»")
        context = context or {}

        drafts_summary = context.get("drafts_summary", "")

        client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.GROQ_API_KEY)

        user_content = (
            f"Основная задача пользователя: {task}\n\n"
            f"--- ПРЕДВАРИТЕЛЬНЫЕ РЕЗУЛЬТАТЫ СУБАГЕНТОВ ДЛЯ АУДИТА ---\n"
            f"{drafts_summary[:4500]}\n"
            f"--------------------------------------------------------\n\n"
            "Внимательно проанализируй эти выводы. "
            "Найди скрытые риски, нестыковки, пропущенные мелочи, скрытые расходы и дай критические исправления."
        )

        try:
            resp = await client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": CRITIC_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                max_tokens=1400
            )
            summary = resp.choices[0].message.content or "Критический анализ не выявил дополнительных рисков."
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка критического анализа: {e}")
            summary = f"Аудит рисков завершился с предупреждением: {e}"

        return AgentResult(
            agent_name=self.name,
            emoji=self.emoji,
            title="Аудит рисков и критический анализ",
            summary=summary.strip()
        )
