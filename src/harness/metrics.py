"""
Datadog metrics emission.

Dead code by default — activates only when DD_API_KEY env var is set.
Uses DogStatsD client from the datadog package.
"""
import os

_ENABLED = bool(os.environ.get("DD_API_KEY"))
_client = None


def _statsd():
    global _client
    if not _ENABLED:
        return None
    if _client is None:
        from datadog import initialize, statsd  # type: ignore
        initialize()
        _client = statsd
    return _client


def _inc(metric: str, tags: list[str] | None = None) -> None:
    s = _statsd()
    if s:
        s.increment(metric, tags=tags or [])


def _hist(metric: str, value: float, tags: list[str] | None = None) -> None:
    s = _statsd()
    if s:
        s.histogram(metric, value, tags=tags or [])


def run_completed(run_id: str, turns: int, tokens: int) -> None:
    _inc("harness.run.completed", [f"run_id:{run_id}"])
    _hist("harness.run.turns", turns)
    _hist("harness.run.tokens", tokens)


def run_failed(run_id: str) -> None:
    _inc("harness.run.failed", [f"run_id:{run_id}"])


def run_awaiting_human(run_id: str) -> None:
    _inc("harness.run.awaiting_human", [f"run_id:{run_id}"])


def alarm_emitted(alarm_type: str, severity: str) -> None:
    _inc("harness.alarm", [f"type:{alarm_type}", f"severity:{severity}"])


def checkpoint_evaluated(stage: str, passed: bool) -> None:
    metric = "harness.checkpoint.passed" if passed else "harness.checkpoint.failed"
    _inc(metric, [f"stage:{stage}"])


def tool_executed(tool_name: str, success: bool) -> None:
    _inc("harness.tool.executed", [f"tool:{tool_name}", f"success:{str(success).lower()}"])
