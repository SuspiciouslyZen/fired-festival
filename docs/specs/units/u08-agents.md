# U8. Agent Implementations

## Dependencies

- [[u01-models]] — `src/agents/base.py` (`BaseAgent`), `src/harness/models.py` (`AgentResponse`, `ToolCall`)

**Files created by this unit:**
- `src/agents/claude_agent.py`
- `src/agents/openai_agent.py`
- `tests/test_agents.py`

---

## File: `src/agents/claude_agent.py`

```python
"""Claude agent using the Anthropic SDK with tool use."""
import os
from anthropic import AsyncAnthropic

from src.agents.base import BaseAgent
from src.harness.models import AgentResponse, ToolCall


class ClaudeAgent(BaseAgent):
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

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

    def supports_tools(self) -> bool:
        return True
```

---

## File: `src/agents/openai_agent.py`

```python
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
```

---

## Tests: `tests/test_agents.py`

Tests should NOT call real APIs. Mock the SDK clients.

1. `ClaudeAgent` raises `ValueError` without `ANTHROPIC_API_KEY`
2. `OpenAIAgent` raises `ValueError` without `OPENAI_API_KEY`
3. Mock a Claude response with tool_use blocks → `AgentResponse` has `tool_calls`
4. Mock an OpenAI response with function calls → `AgentResponse` has `tool_calls`
5. Both agents return valid `AgentResponse` objects (text + usage present)
