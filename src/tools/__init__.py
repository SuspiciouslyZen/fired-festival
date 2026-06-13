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
