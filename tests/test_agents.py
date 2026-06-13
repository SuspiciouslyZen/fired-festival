import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.harness.models import AgentResponse, ToolCall


# 1. ClaudeAgent raises ValueError without ANTHROPIC_API_KEY
def test_claude_agent_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from src.agents.claude_agent import ClaudeAgent
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        ClaudeAgent()


# 2. OpenAIAgent raises ValueError without OPENAI_API_KEY
def test_openai_agent_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.agents.openai_agent import OpenAIAgent
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIAgent()


# 3. Mock Claude response with tool_use blocks → AgentResponse has tool_calls
async def test_claude_agent_tool_use(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    # Build mock response
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "check_status"
    tool_block.input = {"service": "web-api"}

    mock_response = MagicMock()
    mock_response.content = [tool_block]
    mock_response.stop_reason = "tool_use"
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("src.agents.claude_agent.AsyncAnthropic", return_value=mock_client):
        from src.agents.claude_agent import ClaudeAgent
        agent = ClaudeAgent()
        result = await agent.run(
            messages=[{"role": "user", "content": "check web-api"}],
            tools=[{"name": "check_status", "description": "check", "input_schema": {"type": "object", "properties": {}}}],
        )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "check_status"
    assert result.tool_calls[0].arguments == {"service": "web-api"}
    assert result.finish_reason == "tool_use"


# 4. Mock OpenAI response with function calls → AgentResponse has tool_calls
async def test_openai_agent_tool_calls(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import json
    fn_call = MagicMock()
    fn_call.function.name = "read_logs"
    fn_call.function.arguments = json.dumps({"service": "postgres"})

    mock_message = MagicMock()
    mock_message.content = None
    mock_message.tool_calls = [fn_call]

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "tool_calls"

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 80
    mock_usage.completion_tokens = 30

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("src.agents.openai_agent.AsyncOpenAI", return_value=mock_client):
        from src.agents.openai_agent import OpenAIAgent
        agent = OpenAIAgent()
        result = await agent.run(
            messages=[{"role": "user", "content": "read postgres logs"}],
            tools=[{"name": "read_logs", "description": "read logs", "input_schema": {"type": "object", "properties": {}}}],
        )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "read_logs"
    assert result.tool_calls[0].arguments == {"service": "postgres"}


# 5. Both agents return valid AgentResponse objects
async def test_claude_agent_text_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = '{"diagnosis": {"hypothesis": "OOM", "confidence": 0.9}}'

    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.stop_reason = "end_turn"
    mock_response.usage.input_tokens = 200
    mock_response.usage.output_tokens = 60

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("src.agents.claude_agent.AsyncAnthropic", return_value=mock_client):
        from src.agents.claude_agent import ClaudeAgent
        agent = ClaudeAgent()
        result = await agent.run(messages=[{"role": "user", "content": "diagnose"}], tools=[])

    assert isinstance(result, AgentResponse)
    assert result.text is not None
    assert result.usage["input_tokens"] == 200
    assert result.usage["output_tokens"] == 60
    assert result.tool_calls == []
