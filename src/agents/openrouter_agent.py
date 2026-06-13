"""OpenRouter agent — OpenAI-compatible API routing to 100+ models."""
import os
import json
from openai import AsyncOpenAI

from src.agents.base import BaseAgent
from src.harness.models import AgentResponse, ToolCall


class OpenRouterAgent(BaseAgent):
    def __init__(self, model: str | None = None):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")
        self._model = model or os.environ.get("OPENROUTER_MODEL", "openrouter/free")
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "https://fired-festival.railway.app"),
                "X-Title": os.environ.get("OPENROUTER_SITE_NAME", "Ops Runbook Harness"),
            },
        )

    @property
    def agent_name(self) -> str:
        return f"openrouter ({self._model})"

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

        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for tool in tools
        ]

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

    def supports_tools(self) -> bool:
        return True
