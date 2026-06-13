import pytest

from src.harness.guardrails import GuardrailConfig, GuardrailEngine
from src.harness.models import GuardrailDecision
from src.tools import create_registry
from src.tools.registry import ToolDefinition, ToolRegistry


@pytest.fixture
def engine():
    config = GuardrailConfig(
        allowed_actions=["check_status", "restart_service", "read_logs", "kill_query", "flush_dns"],
        requires_approval=["restart_service", "kill_query"],
    )
    return GuardrailEngine(config)


@pytest.fixture
def registry(engine):
    return create_registry(engine)


# 1. Registered tool executes and returns success
async def test_execute_known_tool(registry):
    result = await registry.execute("check_status", {"service": "redis"})
    assert result.success is True
    assert result.output["status"] == "healthy"


# 2. Unknown tool returns success=False
async def test_execute_unknown_tool(registry):
    result = await registry.execute("nonexistent_tool", {})
    assert result.success is False
    assert "Unknown tool" in result.error


# 3. Blocked tool returns guardrail error
async def test_blocked_tool():
    config = GuardrailConfig(allowed_actions=[])
    eng = GuardrailEngine(config)
    reg = create_registry(eng)
    result = await reg.execute("check_status", {"service": "redis"})
    assert result.success is False
    assert "blocked" in result.error.lower()


# 4. NEEDS_APPROVAL tool returns approval-needed result
async def test_needs_approval_tool(registry):
    result = await registry.execute("restart_service", {"service": "web-api"})
    assert result.success is False
    assert result.output.get("needs_approval") is True


# 5. check_status web-api returns degraded with CPU metrics
async def test_check_status_web_api(registry):
    result = await registry.execute("check_status", {"service": "web-api"})
    assert result.success is True
    assert result.output["status"] == "degraded"
    assert "cpu_percent" in result.output


# 6. check_status unknown service returns unknown status
async def test_check_status_unknown_service(registry):
    result = await registry.execute("check_status", {"service": "ghost-svc"})
    assert result.success is True
    assert result.output["status"] == "unknown"


# 7. read_logs postgres returns log lines
async def test_read_logs_postgres(registry):
    result = await registry.execute("read_logs", {"service": "postgres"})
    assert result.success is True
    assert len(result.output["log_lines"]) > 0
    assert "postgres" in result.output["log_lines"][0]


# 8. get_tool_schemas returns schemas for all 5 tools
def test_get_tool_schemas(registry):
    schemas = registry.get_tool_schemas()
    assert len(schemas) == 5
    names = {s["name"] for s in schemas}
    assert names == {"check_status", "restart_service", "read_logs", "kill_query", "flush_dns"}


# 9. Tool executor that raises returns success=False without crashing
async def test_executor_exception_handled(engine):
    async def bad_executor(args: dict) -> dict:
        raise RuntimeError("simulated failure")

    bad_tool = ToolDefinition(
        name="check_status",
        description="bad",
        parameters={},
        executor=bad_executor,
    )
    reg = ToolRegistry(engine)
    reg.register(bad_tool)
    result = await reg.execute("check_status", {})
    assert result.success is False
    assert "simulated failure" in result.error


# 10. create_registry registers all 5 tools
def test_create_registry_all_tools(registry):
    schemas = registry.get_tool_schemas()
    assert len(schemas) == 5
