# U6. Tool Registry and Mock Tools

## Dependencies

- [[u01-models]] — `src/harness/models.py` (`GuardrailDecision`, `ToolResult`)
- [[u02-guardrails]] — `src/harness/guardrails.py` (`GuardrailEngine`)

**Files created by this unit:**
- `src/tools/registry.py`
- `src/tools/check_status.py`
- `src/tools/restart_service.py`
- `src/tools/read_logs.py`
- `src/tools/kill_query.py`
- `src/tools/flush_dns.py`
- `src/tools/__init__.py` (updated with `create_registry`)
- `tests/test_tools.py`

---

## File: `src/tools/registry.py`

```python
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
```

---

## Mock Tool Files

Each mock tool file exports a `ToolDefinition`. All executors are async functions returning dicts.

**`src/tools/check_status.py`**

```python
from src.tools.registry import ToolDefinition

SERVICE_STATUS = {
    "web-api": {"status": "degraded", "cpu_percent": 94.2, "memory_percent": 67.1, "uptime_hours": 142, "error_rate": 12.3, "p95_latency_ms": 2340},
    "postgres": {"status": "warning", "active_connections": 148, "max_connections": 150, "longest_query_seconds": 3847, "replication_lag_ms": 12},
    "redis": {"status": "healthy", "memory_used_mb": 1024, "hit_rate": 0.97, "connected_clients": 42},
    "cdn": {"status": "degraded", "dns_resolution_ms": 8500, "cache_hit_rate": 0.34, "error_rate": 28.7},
    "worker": {"status": "healthy", "queue_depth": 12, "processing_rate": 45.2},
    "gateway": {"status": "healthy", "requests_per_second": 1240, "error_rate": 0.1},
}


async def _execute(args: dict) -> dict:
    service = args.get("service", "unknown")
    if service in SERVICE_STATUS:
        return {"service": service, **SERVICE_STATUS[service]}
    return {"service": service, "status": "unknown", "error": f"Service '{service}' not found"}


definition = ToolDefinition(
    name="check_status",
    description="Check the current health status and metrics of a service",
    parameters={
        "service": {"type": "string", "description": "Name of the service to check (e.g., 'web-api', 'postgres')"}
    },
    executor=_execute,
)
```

**`src/tools/restart_service.py`**

```python
from src.tools.registry import ToolDefinition


async def _execute(args: dict) -> dict:
    service = args.get("service", "unknown")
    return {
        "service": service,
        "action": "restart",
        "result": "success",
        "message": f"Service '{service}' restarted successfully",
        "new_status": "healthy",
        "restart_duration_seconds": 4.2,
    }


definition = ToolDefinition(
    name="restart_service",
    description="Restart a service instance. This is a mutating action.",
    parameters={
        "service": {"type": "string", "description": "Name of the service to restart"}
    },
    executor=_execute,
)
```

**`src/tools/read_logs.py`**

```python
from src.tools.registry import ToolDefinition

SAMPLE_LOGS = {
    "web-api": [
        "2026-06-12T10:23:01Z ERROR [web-api] Request timeout after 30s - GET /api/v2/users",
        "2026-06-12T10:23:02Z ERROR [web-api] CPU throttling detected - container limit reached",
        "2026-06-12T10:23:05Z WARN  [web-api] Connection pool exhausted, queuing requests",
        "2026-06-12T10:23:08Z ERROR [web-api] Health check failed - response time 4200ms > threshold 1000ms",
        "2026-06-12T10:23:12Z INFO  [web-api] Auto-scaling triggered but max instances reached (8/8)",
    ],
    "postgres": [
        "2026-06-12T10:20:00Z WARN  [postgres] Long-running query detected: SELECT * FROM events JOIN... (running 3847s)",
        "2026-06-12T10:21:30Z ERROR [postgres] Connection pool near capacity: 148/150 active connections",
        "2026-06-12T10:22:00Z WARN  [postgres] Lock contention on table 'events' - 12 queries waiting",
        "2026-06-12T10:22:45Z INFO  [postgres] Replication lag stable at 12ms",
    ],
    "cdn": [
        "2026-06-12T10:15:00Z ERROR [cdn] DNS resolution timeout for edge-us-west-2.cdn.example.com",
        "2026-06-12T10:15:30Z ERROR [cdn] Cache miss rate spiked to 66% - possible DNS propagation issue",
        "2026-06-12T10:16:00Z WARN  [cdn] Fallback to origin for 28.7% of requests",
    ],
}


async def _execute(args: dict) -> dict:
    service = args.get("service", "unknown")
    lines = args.get("lines", 10)
    logs = SAMPLE_LOGS.get(service, [f"No logs available for service '{service}'"])
    return {"service": service, "log_lines": logs[:lines], "total_lines": len(logs)}


definition = ToolDefinition(
    name="read_logs",
    description="Read recent log entries for a service",
    parameters={
        "service": {"type": "string", "description": "Name of the service"},
        "lines": {"type": "integer", "description": "Number of recent log lines to return (default 10)"},
    },
    executor=_execute,
)
```

**`src/tools/kill_query.py`**

```python
from src.tools.registry import ToolDefinition


async def _execute(args: dict) -> dict:
    query_id = args.get("query_id", "unknown")
    return {
        "query_id": query_id,
        "action": "kill",
        "result": "success",
        "message": f"Query '{query_id}' terminated",
        "freed_connections": 12,
        "lock_released": True,
    }


definition = ToolDefinition(
    name="kill_query",
    description="Kill a long-running or hung database query. This is a mutating action.",
    parameters={
        "query_id": {"type": "string", "description": "The ID of the query to kill"},
    },
    executor=_execute,
)
```

**`src/tools/flush_dns.py`**

```python
from src.tools.registry import ToolDefinition


async def _execute(args: dict) -> dict:
    service = args.get("service", "unknown")
    return {
        "service": service,
        "action": "flush_dns",
        "result": "success",
        "message": f"DNS cache flushed for '{service}'",
        "dns_resolution_ms_after": 45,
        "propagation_status": "complete",
    }


definition = ToolDefinition(
    name="flush_dns",
    description="Flush DNS cache for a service to resolve DNS propagation issues",
    parameters={
        "service": {"type": "string", "description": "Name of the service with DNS issues"},
    },
    executor=_execute,
)
```

---

## File: `src/tools/__init__.py`

```python
"""Register all tools with the registry."""
from src.harness.guardrails import GuardrailEngine
from src.tools.registry import ToolRegistry
from src.tools import check_status, restart_service, read_logs, kill_query, flush_dns


def create_registry(guardrails: GuardrailEngine) -> ToolRegistry:
    registry = ToolRegistry(guardrails)
    registry.register(check_status.definition)
    registry.register(restart_service.definition)
    registry.register(read_logs.definition)
    registry.register(kill_query.definition)
    registry.register(flush_dns.definition)
    return registry
```

---

## Tests: `tests/test_tools.py`

1. Registered tool executes and returns `success=True` with output
2. Unknown tool returns `success=False` with error message
3. Blocked tool (not on allow-list) returns `success=False` with guardrail error — mock a guardrail engine that blocks it
4. Tool returning `NEEDS_APPROVAL` returns the approval-needed result
5. `check_status("web-api")` returns degraded status with CPU metrics
6. `check_status("unknown-svc")` returns unknown status
7. `read_logs("postgres")` returns log lines
8. `get_tool_schemas()` returns schemas for all registered tools
9. Tool executor that raises exception returns `success=False` without crashing
10. `create_registry()` creates registry with all 5 tools registered
