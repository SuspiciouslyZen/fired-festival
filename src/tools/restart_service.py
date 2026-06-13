from src.tools.registry import ToolDefinition
from src.harness.run_state import RunState


def make_definition(state: RunState) -> ToolDefinition:
    async def _execute(args: dict) -> dict:
        service = args.get("service", "unknown")

        # If this service maps to a real EC2 instance, start it via AWS API
        try:
            from src.aws.discovery import get_service_instance_map
            instance_id = get_service_instance_map().get(service)
            if instance_id:
                import asyncio
                from src.aws.ec2 import start_ec2_instance
                result = await asyncio.to_thread(start_ec2_instance, instance_id)
                return {
                    "service": service,
                    "action": "start",
                    "instance_id": instance_id,
                    **result,
                }
        except Exception as e:
            pass

        # Fall back to mock state for non-EC2 services
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
