"""
Per-run mutable service state store.

Seeded from "failed" or "stable" at run creation time.
Tools read and write to this — check_status reads it,
remediation tools (restart_service, kill_query, flush_dns) transition it to stable.
"""

FAILED: dict[str, dict] = {
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
        "status": "degraded",
        "requests_per_second": 1240,
        "error_rate_pct": 18.4,
        "p99_latency_ms": 3200,
    },
}

STABLE: dict[str, dict] = {
    "web-api": {
        "status": "healthy",
        "cpu_percent": 11.4,
        "cpu_steal_percent": 0.3,
        "memory_percent": 42.1,
        "uptime_hours": 0.1,
        "error_rate_5xx_pct": 0.1,
        "p99_latency_ms": 38,
        "asg_instances_running": 6,
        "asg_instances_max": 8,
        "healthcheck": "OK",
    },
    "postgres": {
        "status": "healthy",
        "active_connections": 44,
        "max_connections": 150,
        "longest_query_seconds": 0,
        "queries_waiting_on_lock": 0,
        "lock_relation": None,
        "lock_pid": None,
        "replication_lag_seconds": 0.8,
        "replica": "prod-db-replica-1",
    },
    "redis": {
        "status": "healthy",
        "used_memory_mb": 9216,
        "maxmemory_mb": 16384,
        "memory_utilization_pct": 56.2,
        "fragmentation_ratio": 1.08,
        "hit_rate_pct": 94.1,
        "hit_rate_baseline_pct": 94.1,
        "evicted_keys_last_60s": 0,
        "connected_clients": 841,
        "client_limit": 3000,
        "latency_p99_ms": 2,
    },
    "cdn": {
        "status": "healthy",
        "dns_resolution_ms": 42,
        "cache_hit_rate_pct": 91.3,
        "origin_fallback_pct": 1.2,
        "affected_edge": None,
    },
    "worker": {
        "status": "healthy",
        "queue_name": "email_notifications",
        "queue_depth": 312,
        "queue_depth_threshold": 10000,
        "workers_running": 24,
        "workers_expected": 24,
        "oom_kills_last_30m": 0,
        "job_failure_rate_pct": 0.3,
        "dlq_depth": 0,
        "drain_estimate_hours": 0.1,
    },
    "gateway": {
        "status": "healthy",
        "requests_per_second": 1240,
        "error_rate_pct": 0.1,
        "p99_latency_ms": 18,
    },
}


class RunState:
    """Mutable per-run state store. Tools read and write to this."""

    def __init__(self, service: str, initial: str = "failed"):
        template = FAILED if initial == "failed" else STABLE
        self._states: dict[str, dict] = {
            svc: data.copy() for svc, data in template.items()
        }
        # Ensure the alert's service is seeded even if not in templates
        if service not in self._states:
            self._states[service] = {"status": "degraded" if initial == "failed" else "healthy"}

    def get(self, service: str) -> dict:
        return self._states.get(service, {"status": "unknown"}).copy()

    def recover(self, service: str) -> None:
        stable = STABLE.get(service)
        if stable:
            self._states[service] = stable.copy()
