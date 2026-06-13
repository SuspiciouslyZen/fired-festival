from src.tools.registry import ToolDefinition
from src.harness.run_state import RunState


def make_definition(state: RunState) -> ToolDefinition:
    async def _execute(args: dict) -> dict:
        service = args.get("service", "cdn")
        state.recover(service)
        post = state.get(service)
        return {
            "service": service,
            "action": "flush_dns",
            "result": "success",
            "message": f"DNS cache flushed for '{service}'",
            "post_flush_status": post,
        }

    return ToolDefinition(
        name="flush_dns",
        description="Flush DNS cache for a service to resolve DNS propagation issues",
        parameters={
            "service": {"type": "string", "description": "Name of the service with DNS issues"},
        },
        executor=_execute,
    )
