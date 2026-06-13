"""Claude agent using the Anthropic SDK with tool use."""
import os
from anthropic import AsyncAnthropic

from src.agents.base import BaseAgent
from src.harness.models import AgentResponse, ToolCall


class ClaudeAgent(BaseAgent):
    def __init__(self, model: str | None = None):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    async def run(self, messages: list[dict], tools: list[dict]) -> AgentResponse:
        # Convert messages to Anthropic format
        system_msg = ""
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            elif msg["role"] == "assistant":
                api_messages.append({"role": "assistant", "content": msg["content"]})
            elif msg["role"] in ("user", "tool"):
                # Tool results become user messages with tool_result content blocks
                if msg["role"] == "tool":
                    # If the last message is a user role, append to it; otherwise create new
                    tool_result_block = {
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_use_id", "unknown"),
                        "content": msg["content"],
                    }
                    if api_messages and api_messages[-1]["role"] == "user":
                        content = api_messages[-1]["content"]
                        if isinstance(content, str):
                            api_messages[-1]["content"] = [{"type": "text", "text": content}, tool_result_block]
                        elif isinstance(content, list):
                            content.append(tool_result_block)
                    else:
                        api_messages.append({"role": "user", "content": [tool_result_block]})
                else:
                    api_messages.append({"role": "user", "content": msg["content"]})

        # Convert tools to Anthropic format
        anthropic_tools = []
        for tool in tools:
            anthropic_tools.append({
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool.get("input_schema", {"type": "object", "properties": {}}),
            })

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_msg,
            messages=api_messages if api_messages else [{"role": "user", "content": "Begin."}],
            tools=anthropic_tools if anthropic_tools else None,
        )

        # Parse response
        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(tool_name=block.name, arguments=block.input))

        return AgentResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    @property
    def agent_name(self) -> str:
        return f"claude ({self._model})"

    def supports_tools(self) -> bool:
        return True
