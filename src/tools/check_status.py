from src.tools.registry import ToolDefinition

SERVICE_STATUS = {
    "web-api": {
        "status": "degraded",
        "cpu_percent": 94.2,
        "cpu_steal_percent": 16.1,
        "memory_percent": 67.1,
        "uptime_hours": 142,
        "error_rate_5xx_pct": 12.3,
        "p99_latency_ms": 4820,
        "asg_instances_running": 8,
        "asg_instances_max": 8,
        "healthcheck": "FAILING",
    },
    "postgres": {
        "status": "critical",
        "active_connections": 148,
        "max_connections": 150,
        "longest_query_seconds": 3847,
        "queries_waiting_on_lock": 14,
        "lock_relation": "events",
        "lock_pid": 31447,
        "replication_lag_seconds": 47,
        "replica": "prod-db-replica-1",
    },
    "redis": {
        "status": "critical",
        "used_memory_mb": 14464,
        "maxmemory_mb": 16384,
        "memory_utilization_pct": 88.2,
        "fragmentation_ratio": 3.42,
        "hit_rate_pct": 61.3,
        "hit_rate_baseline_pct": 94.1,
        "evicted_keys_last_60s": 48302,
        "connected_clients": 2841,
        "client_limit": 3000,
        "latency_p99_ms": 94,
    },
    "cdn": {
        "status": "degraded",
        "dns_resolution_ms": 8500,
        "cache_hit_rate_pct": 34.0,
        "origin_fallback_pct": 28.7,
        "affected_edge": "us-west-2",
    },
    "worker": {
        "status": "critical",
        "queue_name": "email_notifications",
        "queue_depth": 94203,
        "queue_depth_threshold": 10000,
        "workers_running": 12,
        "workers_expected": 24,
        "oom_kills_last_30m": 12,
        "job_failure_rate_pct": 34.1,
        "dlq_depth": 2109,
        "drain_estimate_hours": 6.4,
    },
    "gateway": {
        "status": "healthy",
        "requests_per_second": 1240,
        "error_rate_pct": 0.1,
        "p99_latency_ms": 18,
    },
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
