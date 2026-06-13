from src.tools.registry import ToolDefinition
from src.harness.run_state import RunState


def make_definition(state: RunState) -> ToolDefinition:
    async def _execute(args: dict) -> dict:
        service = args.get("service", "unknown")
        return {"service": service, **state.get(service)}

    return ToolDefinition(
        name="check_status",
        description="Check the current health status and metrics of a service",
        parameters={
            "service": {"type": "string", "description": "Name of the service to check"},
        },
        executor=_execute,
    )
