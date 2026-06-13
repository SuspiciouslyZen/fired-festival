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
