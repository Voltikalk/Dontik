import logging
from typing import Optional, Dict, Any
from openai import AsyncOpenAI

from bot.config import settings
from .base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

DOC_FINANCE_PROMPT = """Ты — субагент финансовой экспертизы, аудита смет и калькуляции расходов.
Твоя задача — предоставить строгий финансово-экономический расчет:
1. Сметная стоимость (материалы, запчасти, работы мастеров / своими руками).
2. Анализ экономии (где можно сэкономить без потери качества, а на чем экономить категорически нельзя).
3. Проверка соответствия объемов и цен (рыночные цены vs завышенные расценки).
4. Резерв на непредвиденные расходы (+10-15%).
5. Итоговый структурированный бюджет с точной суммой или вилкой цен.

ФОРМАТИРОВАНИЕ:
- Используй понятные таблицы или списки с суммами в рублях (₽).
- Выделяй итоговые суммы жирным (**Итого: 15 400 ₽**).
- Никакого сырого LaTeX кода, используй простые символы (², ³, ≈, ·).
"""


class DocFinanceAgent(BaseAgent):
    """Субагент расчета смет, финансовых оценок и аудита расходов."""

    def __init__(self):
        super().__init__(
            name="DocFinance",
            emoji="📊",
            description="Финансовый аудит, калькуляция смет, проверка цен в таблицах/ведомостях и оптимизация бюджета."
        )

    async def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        logger.info(f"[{self.name}] Запуск субагента для задачи: «{task[:80]}»")
        context = context or {}

        doc_data = context.get("doc_data", "")
        search_summary = context.get("search_summary", "")

        client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.GROQ_API_KEY)

        user_content = f"Финансовая задача / расчет: {task}"
        if doc_data:
            user_content += f"\n\n--- ДАННЫЕ ИЗ ДОКУМЕНТА/СМЕТЫ ---\n{doc_data[:4000]}"
        if search_summary:
            user_content += f"\n\n--- ОРИЕНТИРЫ РЫНОЧНЫХ ЦЕН ---\n{search_summary[:2000]}"

        try:
            resp = await client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": DOC_FINANCE_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                max_tokens=1400
            )
            summary = resp.choices[0].message.content or "Не удалось рассчитать смету."
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка финансового анализа: {e}")
            summary = f"Ошибка финансового анализа: {e}"

        return AgentResult(
            agent_name=self.name,
            emoji=self.emoji,
            title="Финансовый расчет и аудит сметы",
            summary=summary.strip()
        )
