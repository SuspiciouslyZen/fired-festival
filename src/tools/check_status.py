from src.tools.registry import ToolDefinition

SERVICE_STATUS = {
    "web-api": {"status": "degraded", "cpu_percent": 94.2, "memory_percent": 67.1, "uptime_hours": 142, "error_rate": 12.3, "p95_latency_ms": 2340},
    "postgres": {"status": "warning", "active_connections": 148, "max_connections": 150, "longest_query_seconds": 3847, "replication_lag_ms": 12},
    "redis": {"status": "healthy", "memory_used_mb": 1024, "hit_rate": 0.97, "connected_clients": 42},
    "cdn": {"status": "degraded", "dns_resolution_ms": 8500, "cache_hit_rate": 0.34, "error_rate": 28.7},
    "worker": {"status": "healthy", "queue_depth": 12, "processing_rate": 45.2},
    "gateway": {"status": "healthy", "requests_per_second": 1240, "error_rate": 0.1},
}


async def _execute(args: dict) -> dict:
    service = args.get("service", "unknown")
    if service in SERVICE_STATUS:
        return {"service": service, **SERVICE_STATUS[service]}
    return {"service": service, "status": "unknown", "error": f"Service '{service}' not found"}


definition = ToolDefinition(
    name="check_status",
    description="Check the current health status and metrics of a service",
    parameters={
        "service": {"type": "string", "description": "Name of the service to check (e.g., 'web-api', 'postgres')"}
    },
    executor=_execute,
)
