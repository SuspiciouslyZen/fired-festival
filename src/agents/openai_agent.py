"""OpenAI agent for swap demo — proves the harness is agent-agnostic."""
import os
import json
from openai import AsyncOpenAI

from src.agents.base import BaseAgent
from src.harness.models import AgentResponse, ToolCall


class OpenAIAgent(BaseAgent):
    def __init__(self, model: str = "gpt-4o-mini"):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def run(self, messages: list[dict], tools: list[dict]) -> AgentResponse:
        # Convert to OpenAI format
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

    def supports_tools(self) -> bool:
        return True
