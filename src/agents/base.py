from abc import ABC, abstractmethod

from src.harness.models import AgentResponse


class BaseAgent(ABC):
    @abstractmethod
    async def run(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AgentResponse:
        """Call the LLM with messages and tool definitions. Return structured response."""
        ...

    @abstractmethod
    def supports_tools(self) -> bool:
        """Whether this agent supports tool calling."""
        ...
