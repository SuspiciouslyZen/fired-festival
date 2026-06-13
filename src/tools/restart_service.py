from src.tools.registry import ToolDefinition
from src.harness.run_state import RunState


def make_definition(state: RunState) -> ToolDefinition:
    async def _execute(args: dict) -> dict:
        service = args.get("service", "unknown")
        state.recover(service)
        post = state.get(service)
        return {
            "service": service,
            "action": "restart",
            "result": "success",
            "message": f"Service '{service}' restarted successfully",
            "restart_duration_seconds": 4.2,
            "post_restart_status": post,
        }

    return ToolDefinition(
        name="restart_service",
        description="Restart a service instance. This is a mutating action.",
        parameters={
            "service": {"type": "string", "description": "Name of the service to restart"},
            "reason": {"type": "string", "description": "Reason for the restart"},
        },
        executor=_execute,
    )
