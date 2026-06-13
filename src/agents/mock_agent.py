"""
Scripted mock agent for local testing without an API key.

Cycles through a realistic diagnosis → plan → execute → resolve sequence
so the full harness loop runs end-to-end.
"""
from src.agents.base import BaseAgent
from src.harness.models import AgentResponse, ToolCall


class MockAgent(BaseAgent):
    def __init__(self):
        self._turn = 0

    async def run(self, messages: list[dict], tools: list[dict]) -> AgentResponse:
        self._turn += 1

        # Infer service from the alert in message history
        service = "web-api"
        for msg in messages:
            if msg.get("role") == "user" and "service" in str(msg.get("content", "")):
                content = str(msg["content"])
                for svc in ["postgres", "redis", "cdn", "worker", "gateway", "web-api"]:
                    if svc in content:
                        service = svc
                        break

        if self._turn == 1:
            return AgentResponse(
                tool_calls=[ToolCall(tool_name="check_status", arguments={"service": service})],
                usage={"input_tokens": 120, "output_tokens": 30},
            )
        if self._turn == 2:
            return AgentResponse(
                tool_calls=[ToolCall(tool_name="read_logs", arguments={"service": service, "lines": 5})],
                usage={"input_tokens": 200, "output_tokens": 40},
            )
        if self._turn == 3:
            return AgentResponse(
                text='{"diagnosis": {"hypothesis": "Service is degraded due to resource exhaustion based on status metrics and error logs", "confidence": 0.85, "evidence": ["elevated error rate in logs", "status shows degraded"]}}',
                usage={"input_tokens": 350, "output_tokens": 80},
            )
        if self._turn == 4:
            return AgentResponse(
                text='{"plan": {"actions": ["check_status", "read_logs"], "rationale": "Gather current state before any remediation"}}',
                usage={"input_tokens": 400, "output_tokens": 60},
            )
        # Turn 5+: resolve
        return AgentResponse(
            text='{"resolution": {"status": "resolved", "summary": "Incident investigated. Root cause identified as resource exhaustion. Monitoring in place."}}',
            usage={"input_tokens": 500, "output_tokens": 70},
        )

    def supports_tools(self) -> bool:
        return True
