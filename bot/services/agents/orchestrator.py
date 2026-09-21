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
from .critic_agent import CriticAgent
from .llm_helper import call_subagent_llm

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """Ты — главный Агент-Оркестратор («Пётр — Советник»).
Ты объединяешь выводы и рекомендации специализированных субагентов в единый, глубоко продуманный, выверенный и удобный для чтения финальный отчет в Telegram.

ТВОЯ ЗАДАЧА:
1. Краткое резюме сути (2-3 предложения с ключевыми выводами).
2. Раздел глубоких размышлений и аудита рисков (Thinking / Risk Audit):
   💡 **Анализ рисков и скрытые нюансы:**
   - Неочевидные подводные камни, которые выявил Критик (закисшие болты, ошибки новичков, скрытые расходы, техника безопасности).
3. Сводный раздел с практическими решениями:
   - 🔧 Технический регламент и инструмент
   - 💰 Цены, артикулы и смета расходов
   - 📋 Пошаговый план и сроки
4. Главный совет мастера и итоговая рекомендация.

ПРАВИЛА ОФОРМЛЕНИЯ:
- Красивое разделение блоков через эмодзи и заголовки.
- Выделение важных сумм, артикулов и терминов жирным шрифтом (**жирный текст**).
- Не используй широкие markdown-таблицы с символами (|). Telegram не поддерживает таблицы, они ломаются. Оформляй списки через аккуратные маркеры (• **Позиция**: цена, параметры).
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
        self.critic_agent = CriticAgent()

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

        # --- ЭТАП 3: Глубокое мышление, поиск рисков и критика (Reflexion) ---
        if on_progress:
            await on_progress("🧠 <i>[Анализ рисков] Проверяю расчеты, технологию и скрытые подводные камни...</i>")

        preliminary_blocks = []
        for k, res in results.items():
            preliminary_blocks.append(f"[{res.emoji} {res.title}]:\n{res.summary}")
        preliminary_text = "\n\n".join(preliminary_blocks)

        try:
            critic_res = await self.critic_agent.run(task, {"drafts_summary": preliminary_text})
            results["critic"] = critic_res
        except Exception as e:
            logger.error(f"[Orchestrator] Ошибка субагента-критика: {e}")

        # --- ЭТАП 4: Финальный синтез результатов Оркестратором ---
        if on_progress:
            await on_progress("⚡ <i>Оркестратор объединяет проверенные выводы и формирует финальный вердикт...</i>")

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

        try:
            final_report = await call_subagent_llm(
                system_prompt=SYNTHESIS_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=1200,
                preferred_model="openai/gpt-oss-120b"
            )
            # Если вернулась ошибка о перегрузке, формируем красивый сводный отчет из ответов субагентов
            if "временной перегрузки серверов" in final_report or not final_report.strip():
                final_report = "**Итоги работы субагентов:**\n\n" + "\n\n".join(res.to_formatted_block() for res in results.values())
        except Exception as e:
            logger.error(f"[Orchestrator] Ошибка синтеза: {e}")
            final_report = "**Итоги работы субагентов:**\n\n" + "\n\n".join(res.to_formatted_block() for res in results.values())

        # Добавляем блок проверенных источников (исключаем технические ссылки groq/api)
        clean_sources = [s for s in all_sources if "groq.com" not in s and "openai.com" not in s]
        unique_sources = list(dict.fromkeys(clean_sources))[:4]
        if unique_sources:
            sources_str = "\n".join(f"• {s}" for s in unique_sources)
            final_report += f"\n\n🔗 **Источники и ориентиры цен:**\n{sources_str}"

        # Добавляем плашку задействованных агентов
        active_badges = " | ".join(f"{res.emoji} {res.agent_name}" for res in results.values())
        final_report = f"🤖 **Команда субагентов:** [{active_badges}]\n\n" + final_report

        return final_report
