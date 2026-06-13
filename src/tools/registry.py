"""
Tool registration, schema exposure, and allow-list enforcement.

The registry holds all available tools. The loop calls execute()
which checks guardrails BEFORE running the tool function.

Each tool is registered with:
- name: string identifier (matches guardrails.yaml allow-list)
- description: what the tool does (sent to the LLM)
- parameters: JSON Schema dict of the tool's parameters (sent to the LLM)
- executor: async callable(args_dict) -> dict
"""
from typing import Any, Callable, Awaitable

from src.harness.guardrails import GuardrailEngine
from src.harness.models import GuardrailDecision, ToolResult


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        executor: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.executor = executor

    def to_llm_schema(self) -> dict:
        """Return the schema dict sent to the LLM for tool calling."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self, guardrails: GuardrailEngine):
        self._tools: dict[str, ToolDefinition] = {}
        self._guardrails = guardrails

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool_schemas(self) -> list[dict]:
        """Return all tool schemas for the LLM."""
        return [t.to_llm_schema() for t in self._tools.values()]

    async def execute(self, tool_name: str, arguments: dict[str, Any], environment: str | None = None) -> ToolResult:
        """
        Execute a tool call. Checks guardrails first.
        Returns ToolResult — never raises on tool errors.
        """
        if tool_name not in self._tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        decision = self._guardrails.check_action(tool_name, environment)
        if decision == GuardrailDecision.BLOCKED:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Action blocked by guardrails: {tool_name} is not on the allowed actions list",
            )
        if decision == GuardrailDecision.NEEDS_APPROVAL:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Action requires human approval: {tool_name}",
                output={"needs_approval": True},
            )

        try:
            result_data = await self._tools[tool_name].executor(arguments)
            return ToolResult(tool_name=tool_name, success=True, output=result_data)
        except Exception as e:
            return ToolResult(tool_name=tool_name, success=False, error=str(e))
