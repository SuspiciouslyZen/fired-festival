"""Register all tools with the registry."""
from src.harness.guardrails import GuardrailEngine
from src.harness.run_state import RunState
from src.tools.registry import ToolRegistry
from src.tools import restart_service, read_logs, kill_query, flush_dns, check_status


def create_registry(guardrails: GuardrailEngine, service: str = "unknown", initial_state: str = "failed") -> ToolRegistry:
    state = RunState(service=service, initial=initial_state)
    registry = ToolRegistry(guardrails)
    registry.register(check_status.make_definition(state))
    registry.register(restart_service.make_definition(state))
    registry.register(read_logs.definition)
    registry.register(kill_query.make_definition(state))
    registry.register(flush_dns.make_definition(state))
    return registry
