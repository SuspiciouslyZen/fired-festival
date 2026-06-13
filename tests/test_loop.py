import pytest

from src.agents.base import BaseAgent
from src.db.store import CheckpointStore
from src.harness.guardrails import GuardrailConfig, GuardrailEngine
from src.harness.loop import HarnessLoop
from src.harness.models import AgentResponse, Alert, RunStatus, ToolCall
from src.tools import create_registry


class MockAgent(BaseAgent):
    """Agent that returns pre-scripted responses in sequence."""
    def __init__(self, responses: list[AgentResponse]):
        self._responses = list(responses)
        self._call_count = 0

    async def run(self, messages, tools) -> AgentResponse:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return AgentResponse(text="I don't know what to do next.")

    def supports_tools(self) -> bool:
        return True


@pytest.fixture
async def store():
    s = CheckpointStore(db_path=":memory:")
    await s.connect()
    yield s
    await s.close()


@pytest.fixture
def engine():
    config = GuardrailConfig(
        allowed_actions=["check_status", "restart_service", "read_logs", "kill_query", "flush_dns"],
        requires_approval=["restart_service", "kill_query"],
        max_turns=15,
        token_budget=50000,
    )
    return GuardrailEngine(config)


@pytest.fixture
def registry(engine):
    return create_registry(engine)


@pytest.fixture
def alert():
    return Alert(service="web-api", severity="high", description="High CPU usage detected")


def make_loop(agent, store, engine, registry):
    return HarnessLoop(agent=agent, guardrails=engine, store=store, registry=registry)


# 1. Happy path: full resolution
async def test_happy_path(store, engine, registry, alert):
    responses = [
        # Turn 1: check status
        AgentResponse(tool_calls=[ToolCall(tool_name="check_status", arguments={"service": "redis"})]),
        # Turn 2: read logs
        AgentResponse(tool_calls=[ToolCall(tool_name="read_logs", arguments={"service": "web-api"})]),
        # Turn 3: diagnosis
        AgentResponse(text='{"diagnosis": {"hypothesis": "CPU throttling due to connection pool exhaustion", "confidence": 0.85, "evidence": ["error logs", "high CPU"]}}'),
        # Turn 4: plan
        AgentResponse(text='{"plan": {"actions": ["check_status", "read_logs"], "rationale": "gather more info"}}'),
        # Turn 5: resolution (no second check_status — metrics_after empty, CP4 defaults healthy)
        AgentResponse(text='{"resolution": {"status": "resolved", "summary": "Issue resolved after investigation"}}'),
    ]
    agent = MockAgent(responses)
    loop = make_loop(agent, store, engine, registry)
    result = await loop.run(alert)

    assert result["status"] == RunStatus.COMPLETED.value
    assert "report" in result
    assert result["report"]["run_id"] == result["run_id"]
    cp_stages = [c["stage"] for c in result["checkpoints"]]
    assert "CP1_ALERT_PARSED" in cp_stages
    assert "CP2_HYPOTHESIS_FORMED" in cp_stages
    assert "CP3_PLAN_VALIDATED" in cp_stages
    assert "CP4_HEALTH_CHECK" in cp_stages


# 2. Blocked action → DESTRUCTIVE_ACTION_REQUESTED → AWAITING_HUMAN
async def test_blocked_action_escalates(store, engine, registry, alert):
    responses = [
        AgentResponse(tool_calls=[ToolCall(tool_name="delete_database", arguments={})]),
    ]
    agent = MockAgent(responses)
    loop = make_loop(agent, store, engine, registry)
    result = await loop.run(alert)

    assert result["status"] == RunStatus.AWAITING_HUMAN.value
    alarm_types = [a["type"] for a in result["alarms"]]
    assert "DESTRUCTIVE_ACTION_REQUESTED" in alarm_types


# 3. Turn limit → TURN_LIMIT_REACHED → FAILED
async def test_turn_limit_fails(store, alert):
    config = GuardrailConfig(
        allowed_actions=["check_status", "restart_service", "read_logs", "kill_query", "flush_dns"],
        max_turns=3,
        token_budget=50000,
    )
    eng = GuardrailEngine(config)
    reg = create_registry(eng)
    # Agent always returns empty text — no progress
    responses = [AgentResponse(text="thinking...") for _ in range(20)]
    agent = MockAgent(responses)
    loop = make_loop(agent, store, eng, reg)
    result = await loop.run(alert)

    assert result["status"] == RunStatus.FAILED.value
    alarm_types = [a["type"] for a in result["alarms"]]
    assert "TURN_LIMIT_REACHED" in alarm_types


# 4. Low confidence → CONFIDENCE_LOW alarm, agent prompted to gather more evidence
async def test_low_confidence_emits_alarm(store, engine, registry, alert):
    responses = [
        AgentResponse(text='{"diagnosis": {"hypothesis": "maybe something", "confidence": 0.3, "evidence": []}}'),
        # After being prompted, agent times out
        *[AgentResponse(text="still thinking") for _ in range(20)],
    ]
    agent = MockAgent(responses)
    loop = make_loop(agent, store, engine, registry)
    result = await loop.run(alert)

    alarm_types = [a["type"] for a in result["alarms"]]
    assert "CONFIDENCE_LOW" in alarm_types


# 5. CP4 failure → REMEDIATION_FAILED → AWAITING_HUMAN
async def test_cp4_failure_escalates(store, engine, registry, alert):
    responses = [
        AgentResponse(tool_calls=[ToolCall(tool_name="check_status", arguments={"service": "web-api"})]),
        AgentResponse(text='{"diagnosis": {"hypothesis": "CPU issue", "confidence": 0.9, "evidence": ["high cpu"]}}'),
        AgentResponse(text='{"plan": {"actions": ["check_status"], "rationale": "verify"}}'),
        # Second check_status returns degraded — metrics_after will be degraded
        AgentResponse(tool_calls=[ToolCall(tool_name="check_status", arguments={"service": "web-api"})]),
        # Resolution with degraded metrics_after → CP4 fails
        AgentResponse(text='{"resolution": {"status": "resolved", "summary": "done"}}'),
    ]
    # Override check_status to always return degraded so metrics_after is degraded
    from src.tools.registry import ToolDefinition, ToolRegistry
    async def degraded_status(args):
        return {"service": args.get("service"), "status": "degraded"}

    config = GuardrailConfig(
        allowed_actions=["check_status", "restart_service", "read_logs", "kill_query", "flush_dns"],
        requires_approval=["restart_service", "kill_query"],
        max_turns=15,
        token_budget=50000,
    )
    eng = GuardrailEngine(config)
    reg = ToolRegistry(eng)
    reg.register(ToolDefinition(name="check_status", description="check", parameters={}, executor=degraded_status))

    agent = MockAgent(responses)
    loop = make_loop(agent, store, eng, reg)
    result = await loop.run(alert)

    assert result["status"] == RunStatus.AWAITING_HUMAN.value
    alarm_types = [a["type"] for a in result["alarms"]]
    assert "REMEDIATION_FAILED" in alarm_types


# 6. _extract_json: code block and bare JSON
def test_extract_json_code_block():
    text = 'Some text\n```json\n{"diagnosis": {"hypothesis": "test", "confidence": 0.9}}\n```\nmore text'
    result = HarnessLoop._extract_json(text)
    assert result is not None
    assert result["diagnosis"]["hypothesis"] == "test"


def test_extract_json_bare():
    text = 'Here is my answer: {"resolution": {"status": "resolved", "summary": "fixed"}}'
    result = HarnessLoop._extract_json(text)
    assert result is not None
    assert result["resolution"]["status"] == "resolved"


def test_extract_json_none():
    assert HarnessLoop._extract_json("no json here at all") is None
