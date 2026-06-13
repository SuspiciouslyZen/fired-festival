"""Ollama agent — uses the OpenAI-compatible local endpoint at http://localhost:11434/v1."""
import os
import json
from openai import AsyncOpenAI

from src.agents.base import BaseAgent
from src.harness.models import AgentResponse, ToolCall


class OllamaAgent(BaseAgent):
    def __init__(self, model: str | None = None):
        self._model = model or os.environ.get("OLLAMA_MODEL", "llama3.2")
        self._base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self._client = AsyncOpenAI(api_key="ollama", base_url=self._base_url)

    async def run(self, messages: list[dict], tools: list[dict]) -> AgentResponse:
        oai_messages = []
        for msg in messages:
            if msg["role"] in ("system", "user", "assistant"):
                oai_messages.append({"role": msg["role"], "content": msg["content"]})
            elif msg["role"] == "tool":
                oai_messages.append({
                    "role": "tool",
                    "content": msg["content"],
                    "tool_call_id": msg.get("tool_call_id", "unknown"),
                })

        oai_tools = []
        for tool in tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            })

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=oai_messages,
            tools=oai_tools if oai_tools else None,
        )

        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    tool_name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        return AgentResponse(
            text=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

    @property
    def agent_name(self) -> str:
        return f"ollama ({self._model})"

    def supports_tools(self) -> bool:
        return True
