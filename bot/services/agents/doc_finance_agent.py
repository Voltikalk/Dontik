import logging
from typing import Optional, Dict, Any
from openai import AsyncOpenAI

from bot.config import settings
from .base_agent import BaseAgent, AgentResult
from .llm_helper import call_subagent_llm

logger = logging.getLogger(__name__)

DOC_FINANCE_PROMPT = """Ты — субагент финансовой экспертизы, аудита смет и калькуляции расходов.
Твоя задача — предоставить строгий финансово-экономический расчет:
1. Сметная стоимость (материалы, запчасти, работы мастеров / своими руками).
2. Анализ экономии (где можно сэкономить без потери качества, а на чем экономить категорически нельзя).
3. Проверка соответствия объемов и цен (рыночные цены vs завышенные расценки).
4. Резерв на непредвиденные расходы (+10-15%).
5. Итоговый структурированный бюджет с точной суммой или вилкой цен.

ФОРМАТИРОВАНИЕ:
- Оформляй позиции четким маркированным списком (не строй широкие markdown-таблицы с символами |):
  • **Позиция**: бренд/артикул — 1 500 ₽ (комментарий)
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

        user_content = f"Финансовая задача / расчет: {task}"
        if doc_data:
            user_content += f"\n\n--- ДАННЫЕ ИЗ ДОКУМЕНТА/СМЕТЫ ---\n{doc_data[:4000]}"
        if search_summary:
            user_content += f"\n\n--- ОРИЕНТИРЫ РЫНОЧНЫХ ЦЕН ---\n{search_summary[:2000]}"

        summary = await call_subagent_llm(
            system_prompt=DOC_FINANCE_PROMPT,
            user_prompt=user_content,
            temperature=0.2,
            max_tokens=750
        )

        return AgentResult(
            agent_name=self.name,
            emoji=self.emoji,
            title="Финансовый расчет и аудит сметы",
            summary=summary.strip()
        )
