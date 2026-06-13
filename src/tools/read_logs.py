from src.tools.registry import ToolDefinition

SAMPLE_LOGS = {
    "web-api": [
        "2026-06-13T02:06:11Z INFO  [web-api] Auto-scaling triggered: desired=8, current=6",
        "2026-06-13T02:07:44Z WARN  [web-api] CPU throttling active on i-0a1b2c3d4e5f60001 — container limit 4000m reached",
        "2026-06-13T02:08:02Z ERROR [web-api] GET /api/v2/events 504 Gateway Timeout after 30002ms (upstream: order-svc)",
        "2026-06-13T02:08:03Z ERROR [web-api] GET /api/v2/users 504 Gateway Timeout after 30001ms",
        "2026-06-13T02:08:17Z WARN  [web-api] Connection pool exhausted (512/512) — queuing inbound requests",
        "2026-06-13T02:09:01Z ERROR [web-api] Health check /healthz response time 4820ms > threshold 1000ms — marked unhealthy",
        "2026-06-13T02:09:14Z WARN  [web-api] CPU steal elevated on i-0a1b2c3d4e5f60002: steal=16.1% (threshold 5%)",
        "2026-06-13T02:10:33Z ERROR [web-api] ELB 5xx rate 12.3% over last 5m (threshold: 1%) — alarm CRITICAL",
        "2026-06-13T02:11:00Z INFO  [web-api] Auto-scaling at max capacity (8/8) — no further scale-out possible",
        "2026-06-13T02:14:33Z INFO  [web-api] PagerDuty incident Q3KL9MXZ opened, escalation_policy=Platform On-Call",
    ],
    "postgres": [
        "2026-06-13T00:05:48Z INFO  [postgres] autovacuum: processing table 'events' (18.4M rows)",
        "2026-06-13T01:05:55Z WARN  [postgres] pid=31447 query duration 3600s — long-running query threshold exceeded",
        "2026-06-13T01:06:00Z WARN  [postgres] lock acquired: relation=events oid=16842 mode=AccessExclusiveLock pid=31447",
        "2026-06-13T01:07:12Z WARN  [postgres] 4 queries waiting on lock held by pid=31447",
        "2026-06-13T01:08:30Z ERROR [postgres] connection pool 140/150 — approaching saturation",
        "2026-06-13T01:09:00Z ERROR [postgres] 8 queries waiting on lock held by pid=31447 (events oid=16842)",
        "2026-06-13T01:09:44Z ERROR [postgres] connection pool 148/150 — new connections timing out after 5s",
        "2026-06-13T01:09:55Z ERROR [postgres] replication lag on prod-db-replica-1: 47s (threshold: 5s)",
        "2026-06-13T01:10:01Z ERROR [postgres] 14 queries waiting on lock held by pid=31447 — deadlock risk elevated",
        "2026-06-13T01:10:10Z INFO  [postgres] Datadog monitor 19283 alarm triggered: connections.waiting > threshold",
    ],
    "redis": [
        "2026-06-13T02:31:05Z INFO  [redis] maxmemory policy=allkeys-lru maxmemory=16106127360 used=14092738560",
        "2026-06-13T02:32:17Z WARN  [redis] fragmentation_ratio=2.71 — memory fragmentation above warning threshold 1.5",
        "2026-06-13T02:33:44Z WARN  [redis] evicted_keys delta=+8302 in last 60s — LRU eviction rate elevated",
        "2026-06-13T02:34:01Z ERROR [redis] fragmentation_ratio=3.42 — CRITICAL threshold exceeded, RSS vs used diverging",
        "2026-06-13T02:34:18Z ERROR [redis] hit_rate dropped: 94.1% -> 78.4% — evictions causing cache misses",
        "2026-06-13T02:35:00Z ERROR [redis] hit_rate=61.3% — downstream services reporting cold-cache latency spikes",
        "2026-06-13T02:35:12Z WARN  [redis] connected_clients=2841 approaching limit=3000",
        "2026-06-13T02:35:30Z ERROR [redis] latency p99=94ms (threshold: 5ms) — command queue backing up",
        "2026-06-13T02:35:44Z WARN  [redis] evicted_keys delta=+48302 in last 60s — eviction storm in progress",
        "2026-06-13T02:36:00Z INFO  [redis] Datadog monitor 38821 alarm triggered: fragmentation_ratio CRITICAL",
    ],
    "cdn": [
        "2026-06-12T10:15:00Z ERROR [cdn] DNS resolution timeout for edge-us-west-2.cdn.example.com (8500ms > 100ms threshold)",
        "2026-06-12T10:15:30Z ERROR [cdn] cache hit rate 34% (baseline 91%) — origin fallback storm in progress",
        "2026-06-12T10:15:58Z WARN  [cdn] 28.7% of requests bypassing edge, hitting origin directly",
        "2026-06-12T10:16:14Z ERROR [cdn] NXDOMAIN responses for static.example.com at edge pop us-west-2",
        "2026-06-12T10:16:45Z INFO  [cdn] Cloudflare alert fired: DNS_RESOLUTION_FAILURE zone=cdn.example.com",
    ],
    "worker": [
        "2026-06-13T02:20:01Z INFO  [worker] queue=email_notifications depth=10842 (threshold=10000) — monitor triggered",
        "2026-06-13T02:21:14Z ERROR [worker] pid=44201 OOM killed — heap exceeded container limit 2048MB",
        "2026-06-13T02:21:15Z INFO  [worker] worker restarting (restart 9/10)",
        "2026-06-13T02:22:30Z ERROR [worker] pid=44318 OOM killed — heap exceeded container limit 2048MB",
        "2026-06-13T02:23:00Z ERROR [worker] job failure rate 34.1% over last 5m (threshold: 2%) — jobs timing out waiting for worker",
        "2026-06-13T02:24:18Z WARN  [worker] queue=email_notifications depth=47203 — drain estimate 3h 11m at current throughput",
        "2026-06-13T02:25:00Z ERROR [worker] 12 of 24 worker processes dead — OOM kills in last 30m",
        "2026-06-13T02:26:44Z ERROR [worker] dead letter queue depth=2109 — unrecoverable job failures accumulating",
        "2026-06-13T02:27:01Z WARN  [worker] queue=email_notifications depth=94203 — drain estimate 6h 22m",
        "2026-06-13T02:51:17Z INFO  [worker] PagerDuty incident Q9XP4WKR opened, escalation_policy=Platform On-Call",
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
