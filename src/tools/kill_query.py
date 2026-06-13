from src.tools.registry import ToolDefinition
from src.harness.run_state import RunState


def make_definition(state: RunState) -> ToolDefinition:
    async def _execute(args: dict) -> dict:
        query_id = args.get("query_id", "unknown")
        state.recover("postgres")
        post = state.get("postgres")
        return {
            "query_id": query_id,
            "action": "kill",
            "result": "success",
            "message": f"Query '{query_id}' terminated — lock released",
            "freed_connections": 104,
            "lock_released": True,
            "post_kill_status": post,
        }

    return ToolDefinition(
        name="kill_query",
        description="Kill a long-running or hung database query. This is a mutating action.",
        parameters={
            "query_id": {"type": "string", "description": "The ID or PID of the query to kill"},
            "reason": {"type": "string", "description": "Reason for killing the query"},
        },
        executor=_execute,
    )
