# U11. Fixture Data

## Dependencies

- [[u01-models]] — `Alert` model schema (fixtures must satisfy it)
- [[u00-project-setup]] — `fixtures/alerts/` directory

**Files created by this unit:**
- `fixtures/alerts/high_cpu_web_api.json`
- `fixtures/alerts/hung_query_postgres.json`
- `fixtures/alerts/dns_failure_cdn.json`
- `fixtures/alerts/unknown_service.json`

---

## `fixtures/alerts/high_cpu_web_api.json`

```json
{
  "service": "web-api",
  "severity": "high",
  "description": "CPU utilization at 94% on web-api service. P95 latency degraded to 2340ms (threshold: 500ms). Auto-scaling at max capacity (8/8 instances). Error rate elevated at 12.3%.",
  "source": "pagerduty",
  "metadata": {
    "incident_id": "PD-2026-4521",
    "triggered_at": "2026-06-12T10:23:00Z",
    "escalation_level": 1,
    "team": "platform"
  }
}
```

---

## `fixtures/alerts/hung_query_postgres.json`

```json
{
  "service": "postgres",
  "severity": "high",
  "description": "Long-running query detected on primary database. Query has been executing for 3847 seconds. Connection pool at 148/150 (98.7% utilization). Lock contention reported on 'events' table with 12 queries waiting.",
  "source": "datadog",
  "metadata": {
    "query_id": "pg-query-8847",
    "database": "production",
    "table": "events"
  }
}
```

---

## `fixtures/alerts/dns_failure_cdn.json`

```json
{
  "service": "cdn",
  "severity": "medium",
  "description": "DNS resolution failures for edge-us-west-2.cdn.example.com. Cache hit rate dropped to 34%. 28.7% of requests falling back to origin server. DNS resolution time: 8500ms (threshold: 100ms).",
  "source": "cloudflare",
  "metadata": {
    "edge_location": "us-west-2",
    "affected_domains": ["cdn.example.com", "static.example.com"]
  }
}
```

---

## `fixtures/alerts/unknown_service.json`

```json
{
  "service": "billing-v3",
  "severity": "critical",
  "description": "Service billing-v3 reporting 100% error rate. All health checks failing.",
  "source": "pagerduty",
  "metadata": {
    "incident_id": "PD-2026-4523"
  }
}
```
