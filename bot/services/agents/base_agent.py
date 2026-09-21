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
        lines = [f"{self.emoji} <b>{self.title}</b>"]
        if self.summary:
            lines.append(self.summary.strip())
        if self.details and self.details.strip() != self.summary.strip():
            lines.append(self.details.strip())
        if self.sources:
            links = "\n".join(f"• {src}" for src in self.sources[:3])
            lines.append(f"<b>Источники:</b>\n{links}")
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
