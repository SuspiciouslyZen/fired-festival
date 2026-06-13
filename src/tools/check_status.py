from src.tools.registry import ToolDefinition
from src.harness.run_state import RunState


def make_definition(state: RunState) -> ToolDefinition:
    async def _execute(args: dict) -> dict:
        service = args.get("service", "unknown")

        # If this service maps to a real EC2 instance, hit the AWS API
        try:
            from src.aws.discovery import get_service_instance_map
            instance_id = get_service_instance_map().get(service)
            if instance_id:
                import asyncio
                from src.aws.ec2 import get_ec2_instance_status
                ec2_status = await asyncio.to_thread(get_ec2_instance_status, instance_id)
                return {"service": service, **ec2_status}
        except Exception:
            pass

        return {"service": service, **state.get(service)}

    return ToolDefinition(
        name="check_status",
        description="Check the current health status and metrics of a service",
        parameters={
            "service": {"type": "string", "description": "Name of the service to check"},
        },
        executor=_execute,
    )
