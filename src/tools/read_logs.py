from src.tools.registry import ToolDefinition

SAMPLE_LOGS = {
    "web-api": [
        "2026-06-12T10:23:01Z ERROR [web-api] Request timeout after 30s - GET /api/v2/users",
        "2026-06-12T10:23:02Z ERROR [web-api] CPU throttling detected - container limit reached",
        "2026-06-12T10:23:05Z WARN  [web-api] Connection pool exhausted, queuing requests",
        "2026-06-12T10:23:08Z ERROR [web-api] Health check failed - response time 4200ms > threshold 1000ms",
        "2026-06-12T10:23:12Z INFO  [web-api] Auto-scaling triggered but max instances reached (8/8)",
    ],
    "postgres": [
        "2026-06-12T10:20:00Z WARN  [postgres] Long-running query detected: SELECT * FROM events JOIN... (running 3847s)",
        "2026-06-12T10:21:30Z ERROR [postgres] Connection pool near capacity: 148/150 active connections",
        "2026-06-12T10:22:00Z WARN  [postgres] Lock contention on table 'events' - 12 queries waiting",
        "2026-06-12T10:22:45Z INFO  [postgres] Replication lag stable at 12ms",
    ],
    "cdn": [
        "2026-06-12T10:15:00Z ERROR [cdn] DNS resolution timeout for edge-us-west-2.cdn.example.com",
        "2026-06-12T10:15:30Z ERROR [cdn] Cache miss rate spiked to 66% - possible DNS propagation issue",
        "2026-06-12T10:16:00Z WARN  [cdn] Fallback to origin for 28.7% of requests",
    ],
}


async def _execute(args: dict) -> dict:
    service = args.get("service", "unknown")
    lines = args.get("lines", 10)
    logs = SAMPLE_LOGS.get(service, [f"No logs available for service '{service}'"])
    return {"service": service, "log_lines": logs[:lines], "total_lines": len(logs)}


definition = ToolDefinition(
    name="read_logs",
    description="Read recent log entries for a service",
    parameters={
        "service": {"type": "string", "description": "Name of the service"},
        "lines": {"type": "integer", "description": "Number of recent log lines to return (default 10)"},
    },
    executor=_execute,
)
