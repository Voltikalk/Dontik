import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable, Awaitable
from openai import AsyncOpenAI

from bot.config import settings
from .base_agent import BaseAgent, AgentResult
from .search_agent import SearchAnalystAgent
from .tech_expert_agent import TechExpertAgent
from .doc_finance_agent import DocFinanceAgent
from .planner_agent import PlannerAgent

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """Ты — главный Агент-Оркестратор («Пётр — Советник»).
Ты объединяешь выводы и рекомендации специализированных субагентов в единый, структурированный, исчерпывающий и удобный для чтения финальный отчет в Telegram.

ТВОЯ ЗАДАЧА:
1. Краткое резюме сути (2-3 предложения с ключевыми выводами).
2. Сводный раздел с ключевыми пунктами от субагентов:
   - Техническая часть и инструмент
   - Цены, артикулы и сметный бюджет
   - Пошаговый план и сроки
3. Главный совет мастера и предупреждения об ошибках.

ПРАВИЛА ОФОРМЛЕНИЯ:
- Красивое разделение блоков через эмодзи и заголовки.
- Выделение важных сумм, артикулов и терминов жирным шрифтом (**жирный текст**).
- Никакого сырого LaTeX, используй понятные символы Unicode (², ³, √, ±, ≈).
- Пиши на живом, уверенном русском языке без канцелярщины.
"""


class MultiAgentOrchestrator:
    """Оркестратор мультиагентной системы для координации субагентов."""

    def __init__(self):
        self.search_agent = SearchAnalystAgent()
        self.tech_agent = TechExpertAgent()
        self.finance_agent = DocFinanceAgent()
        self.planner_agent = PlannerAgent()

    def select_agents_for_task(self, task: str) -> List[str]:
        """
        Определяет, какие субагенты требуются для решения задачи.
        """
        task_lower = task.lower()
        selected = []

        # Поиск цен / аналитики
        search_keywords = ["цен", "стоим", "купи", "рынок", "артикул", "где", "найти", "выбрать", "сравн", "дешев"]
        if any(k in task_lower for k in search_keywords) or len(task) > 50:
            selected.append("search")

        # Техническая экспертиза
        tech_keywords = ["ремонт", "замен", "починить", "установ", "двигател", "мотор", "коробк", "подвеск", "тормоз", "сцеплен", "как сделать", "снять", "поставить", "инструмент", "момент"]
        if any(k in task_lower for k in tech_keywords) or len(task) > 50:
            selected.append("tech")

        # Финансы и сметы
        finance_keywords = ["смет", "бюджет", "расход", "посчитай", "рубл", "выгод", "эконом", "таблиц", "excel", "вор", "пзу"]
        if any(k in task_lower for k in finance_keywords):
            selected.append("finance")

        # Планирование
        plan_keywords = ["план", "этап", "с чего начать", "порядок", "шаг", "подготов", "проект", "чек-лист"]
        if any(k in task_lower for k in plan_keywords):
            selected.append("planner")

        # По умолчанию, если задача сложная — подключаем ключевую тройку
        if not selected:
            selected = ["search", "tech", "finance"]

        return selected

    async def execute_task(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> str:
        """
        Запускает цикл субагентов с поэтапным выполнением и финальным синтезом.
        """
        context = context or {}
        selected_agents = self.select_agents_for_task(task)
        logger.info(f"[Orchestrator] Выбраны субагенты для задачи: {selected_agents}")

        results: Dict[str, AgentResult] = {}

        # --- ЭТАП 1: Поиск информации и техническая экспертиза (параллельно) ---
        stage1_tasks = []
        if "search" in selected_agents:
            stage1_tasks.append(("search", self.search_agent.run(task, context)))
        if "tech" in selected_agents:
            stage1_tasks.append(("tech", self.tech_agent.run(task, context)))

        if stage1_tasks:
            if on_progress:
                active_names = " и ".join("🔍 поиск цен" if k == "search" else "🔧 техэкспертизу" for k, _ in stage1_tasks)
                await on_progress(f"🤖 <i>Задействую субагентов: запускаю {active_names}...</i>")

            stage1_results = await asyncio.gather(*(t[1] for t in stage1_tasks), return_exceptions=True)
            for (key, _), res in zip(stage1_tasks, stage1_results):
                if isinstance(res, AgentResult):
                    results[key] = res
                else:
                    logger.error(f"[Orchestrator] Ошибка субагента {key}: {res}")

        # Обновляем контекст для второго этапа
        stage2_context = dict(context)
        if "search" in results:
            stage2_context["search_summary"] = results["search"].summary
        if "tech" in results:
            stage2_context["tech_summary"] = results["tech"].summary

        # --- ЭТАП 2: Финансовый расчет и стратегическое планирование ---
        stage2_tasks = []
        if "finance" in selected_agents or "search" in results:
            stage2_tasks.append(("finance", self.finance_agent.run(task, stage2_context)))
        if "planner" in selected_agents or len(task) > 40:
            stage2_tasks.append(("planner", self.planner_agent.run(task, stage2_context)))

        if stage2_tasks:
            if on_progress:
                await on_progress("📊 <i>Субагенты рассчитывают бюджет и формируют пошаговый план...</i>")

            stage2_results = await asyncio.gather(*(t[1] for t in stage2_tasks), return_exceptions=True)
            for (key, _), res in zip(stage2_tasks, stage2_results):
                if isinstance(res, AgentResult):
                    results[key] = res
                else:
                    logger.error(f"[Orchestrator] Ошибка субагента {key}: {res}")

        # --- ЭТАП 3: Синтез результатов Оркестратором ---
        if on_progress:
            await on_progress("⚡ <i>Оркестратор формирует итоговый сводный отчет...</i>")

        # Собираем данные всех агентов
        subagent_blocks = []
        all_sources = []
        for key, res in results.items():
            subagent_blocks.append(f"### Выводы субагента [{res.emoji} {res.title}]:\n{res.summary}")
            all_sources.extend(res.sources)

        subagents_text = "\n\n".join(subagent_blocks)
        user_prompt = (
            f"Задача пользователя: {task}\n\n"
            f"--- МАТЕРИАЛЫ ОТ СПЕЦИАЛИЗИРОВАННЫХ СУБАГЕНТОВ ---\n{subagents_text}\n"
            f"--------------------------------------------------\n\n"
            "Объедини материалы субагентов в единый монолитный экспертный отчет. "
            "Дай четкие рекомендации, сводку цен, ключевые этапы и предостережения."
        )

        client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.GROQ_API_KEY)
        try:
            resp = await client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYNTHESIS_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=2200
            )
            final_report = resp.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"[Orchestrator] Ошибка синтеза: {e}")
            final_report = "<b>Итоги работы субагентов:</b>\n\n" + "\n\n".join(res.to_formatted_block() for res in results.values())

        # Добавляем блок использованных источников
        unique_sources = list(dict.fromkeys(all_sources))[:4]
        if unique_sources:
            sources_str = "\n".join(f"• {s}" for s in unique_sources)
            final_report += f"\n\n🔗 <b>Источники и ориентиры цен:</b>\n{sources_str}"

        # Добавляем плашку задействованных агентов
        active_badges = " | ".join(f"{res.emoji} {res.agent_name}" for res in results.values())
        final_report = f"🤖 <b>Команда субагентов:</b> [{active_badges}]\n\n" + final_report

        return final_report
