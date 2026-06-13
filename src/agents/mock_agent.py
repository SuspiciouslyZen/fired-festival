"""
Scripted mock agent for local testing without an API key.

All output is labeled [MOCK] — this is NOT real model output.
Reasoning text is generated from actual tool results in message history
so it reflects real data, but the decision logic is scripted, not learned.
"""
import json
from src.agents.base import BaseAgent
from src.harness.models import AgentResponse, ToolCall


def _extract_tool_output(messages: list[dict], tool_name: str) -> dict | None:
    """Return the parsed output dict from the most recent tool result for tool_name."""
    for msg in reversed(messages):
        if msg.get("role") == "tool" and msg.get("tool_name") == tool_name:
            try:
                parsed = json.loads(msg["content"])
                return parsed.get("output", parsed)
            except Exception:
                return None
    return None


def _infer_service(messages: list[dict]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            content = str(msg.get("content", ""))
            for svc in ["postgres", "redis", "cdn", "worker", "gateway", "web-api"]:
                if f'"service": "{svc}"' in content or f"'service': '{svc}'" in content:
                    return svc
    return "web-api"


class MockAgent(BaseAgent):
    def __init__(self):
        self._turn = 0

    @property
    def agent_name(self) -> str:
        return "mock"

    async def run(self, messages: list[dict], tools: list[dict]) -> AgentResponse:
        self._turn += 1
        service = _infer_service(messages)

        if self._turn == 1:
            return AgentResponse(
                text=f"[MOCK] Starting diagnosis for service '{service}'. Calling check_status to get current health metrics.",
                tool_calls=[ToolCall(tool_name="check_status", arguments={"service": service})],
                usage={"input_tokens": 120, "output_tokens": 30},
            )

        if self._turn == 2:
            status = _extract_tool_output(messages, "check_status") or {}
            status_summary = ", ".join(f"{k}={v}" for k, v in status.items() if k != "service")
            return AgentResponse(
                text=f"[MOCK] check_status returned: {status_summary}. Fetching recent logs to correlate with these metrics.",
                tool_calls=[ToolCall(tool_name="read_logs", arguments={"service": service, "lines": 10})],
                usage={"input_tokens": 200, "output_tokens": 40},
            )

        if self._turn == 3:
            status = _extract_tool_output(messages, "check_status") or {}
            logs = _extract_tool_output(messages, "read_logs") or {}
            log_lines = logs.get("log_lines", [])

            # Build a data-driven hypothesis from actual values
            indicators = []
            for k, v in status.items():
                if k in ("status",) and v in ("degraded", "critical", "warning"):
                    indicators.append(f"service status is {v}")
                if k == "cpu_percent" and isinstance(v, (int, float)) and v > 80:
                    indicators.append(f"CPU at {v}%")
                if k == "fragmentation_ratio" and isinstance(v, (int, float)) and v > 1.5:
                    indicators.append(f"memory fragmentation ratio {v} (threshold 1.5)")
                if k == "hit_rate_pct" and isinstance(v, (int, float)) and v < 80:
                    indicators.append(f"cache hit rate dropped to {v}%")
                if k == "active_connections" and "max_connections" in status:
                    pct = round(v / status["max_connections"] * 100, 1)
                    if pct > 90:
                        indicators.append(f"connection pool {v}/{status['max_connections']} ({pct}% utilized)")
                if k == "longest_query_seconds" and isinstance(v, (int, float)) and v > 300:
                    indicators.append(f"query running for {v}s")
                if k == "queue_depth" and isinstance(v, (int, float)) and v > 1000:
                    indicators.append(f"queue depth {v}")
                if k == "workers_running" and "workers_expected" in status and v < status["workers_expected"]:
                    indicators.append(f"only {v}/{status['workers_expected']} workers running")
                if k == "error_rate_5xx_pct" and isinstance(v, (int, float)) and v > 1:
                    indicators.append(f"5xx error rate {v}%")
                if k == "replication_lag_seconds" and isinstance(v, (int, float)) and v > 5:
                    indicators.append(f"replication lag {v}s")

            evidence_from_logs = [l for l in log_lines if "ERROR" in l or "WARN" in l][:3]
            evidence = indicators + [f'log: "{l.split("] ", 1)[-1]}"' for l in evidence_from_logs]

            hypothesis = f"[MOCK] {service} is in a degraded state. Observed: {'; '.join(indicators) if indicators else 'anomalous metrics across multiple dimensions'}. Log evidence confirms active failure mode."

            return AgentResponse(
                text=hypothesis,
                tool_calls=[],
                usage={"input_tokens": 350, "output_tokens": 80},
            )

        if self._turn == 4:
            status = _extract_tool_output(messages, "check_status") or {}
            svc = _infer_service(messages)

            if "longest_query_seconds" in status:
                tool, args = "kill_query", {"query_id": status.get("lock_pid", "unknown"), "reason": "long-running query holding AccessExclusiveLock"}
                rationale = f"[MOCK] Query running {status.get('longest_query_seconds')}s holds lock on {status.get('lock_relation', 'unknown')} blocking {status.get('queries_waiting_on_lock', '?')} queries. Killing pid {status.get('lock_pid', '?')}."
            elif "fragmentation_ratio" in status:
                tool, args = "restart_service", {"service": svc, "reason": "memory fragmentation eviction storm — restart to reclaim RSS"}
                rationale = f"[MOCK] fragmentation_ratio={status.get('fragmentation_ratio')} with hit_rate={status.get('hit_rate_pct')}% — eviction storm poisoning cache. Restart required."
            elif status.get("cpu_percent", 0) > 80:
                tool, args = "restart_service", {"service": svc, "reason": "cpu throttling at ASG max capacity"}
                rationale = f"[MOCK] CPU {status.get('cpu_percent')}% at ASG max ({status.get('asg_instances_running')}/{status.get('asg_instances_max')}). Restarting to clear throttled container state."
            elif status.get("queue_depth", 0) > 1000:
                tool, args = "restart_service", {"service": svc, "reason": "OOM-killed workers — restarting fleet"}
                rationale = f"[MOCK] {status.get('workers_running')}/{status.get('workers_expected')} workers alive, queue depth {status.get('queue_depth')}. Restarting fleet."
            else:
                tool, args = "restart_service", {"service": svc, "reason": "service degraded"}
                rationale = f"[MOCK] Service degraded. Restarting {svc}."

            return AgentResponse(
                text=rationale,
                tool_calls=[ToolCall(tool_name=tool, arguments=args)],
                usage={"input_tokens": 400, "output_tokens": 60},
            )

        if self._turn == 5:
            status = _extract_tool_output(messages, "check_status") or {}

            if "longest_query_seconds" in status:
                tool = "kill_query"
                args = {"query_id": status.get("lock_pid", "unknown"), "reason": "long-running query holding AccessExclusiveLock on events table"}
            elif "fragmentation_ratio" in status or "hit_rate_pct" in status:
                tool = "restart_service"
                args = {"service": _infer_service(messages), "reason": "memory fragmentation eviction storm — restart required to reclaim RSS"}
            elif "cpu_percent" in status:
                tool = "restart_service"
                args = {"service": _infer_service(messages), "reason": "cpu throttling at max ASG capacity"}
            else:
                tool = "restart_service"
                args = {"service": _infer_service(messages), "reason": "remediation"}

            return AgentResponse(
                text=f"[MOCK] Executing remediation: {tool}({args})",
                tool_calls=[ToolCall(tool_name=tool, arguments=args)],
                usage={"input_tokens": 420, "output_tokens": 50},
            )

        # Turn 6: post-remediation health check
        if self._turn == 6:
            return AgentResponse(
                text="[MOCK] Remediation action dispatched. Running post-remediation health check to verify recovery.",
                tool_calls=[ToolCall(tool_name="check_status", arguments={"service": _infer_service(messages)})],
                usage={"input_tokens": 460, "output_tokens": 30},
            )

        # Turn 7+: resolve based on actual post-remediation status
        post_status = _extract_tool_output(messages, "check_status") or {}
        svc_status = post_status.get("status", "unknown")
        metrics_summary = ", ".join(f"{k}={v}" for k, v in post_status.items() if k not in ("service", "status"))

        return AgentResponse(
            text=f"[MOCK] Post-remediation check_status returned status={svc_status}. Metrics: {metrics_summary}.",
            usage={"input_tokens": 500, "output_tokens": 70},
        )

    def supports_tools(self) -> bool:
        return True
