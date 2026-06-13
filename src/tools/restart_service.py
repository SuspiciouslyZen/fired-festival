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
