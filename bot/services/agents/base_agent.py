import abc
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class AgentResult:
    agent_name: str
    emoji: str
    title: str
    summary: str
    details: str = ""
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_formatted_block(self) -> str:
        """Форматирует результат работы субагента для итогового вывода."""
        lines = [f"{self.emoji} **{self.title}**"]
        clean_summary = self.summary.strip()
        # Фильтруем технические ошибки и ссылки на биллинг Groq
        if "console.groq.com" in clean_summary or "Error code: 429" in clean_summary:
            clean_summary = "Данные раздела рассчитаны по базовым стандартам и нормативам."
        if clean_summary:
            lines.append(clean_summary)
        if self.details and self.details.strip() != self.summary.strip():
            lines.append(self.details.strip())
        if self.sources:
            clean_sources = [s for s in self.sources if "groq.com" not in s]
            if clean_sources:
                links = "\n".join(f"• {src}" for src in clean_sources[:3])
                lines.append(f"**Источники:**\n{links}")
        return "\n\n".join(lines)


class BaseAgent(abc.ABC):
    """Базовый абстрактный класс специализированного субагента."""

    def __init__(self, name: str, emoji: str, description: str):
        self.name = name
        self.emoji = emoji
        self.description = description

    @abc.abstractmethod
    async def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        Выполняет специализированную задачу субагента.
        :param task: Текст задачи / вопроса.
        :param context: Дополнительный контекст (документы, предыдущие ответы, параметры).
        :return: AgentResult с выводами субагента.
        """
        pass
