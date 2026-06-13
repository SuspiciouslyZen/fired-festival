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
