"""
Alarm emission and collection.

AlarmManager collects alarms for a single run. It determines
severity from AlarmType using a default mapping (overridable via
guardrails config severity_overrides).

Key behavior: emit() returns should_halt (bool). CRITICAL severity
halts the loop; WARNING and INFO do not.
"""
from src.harness.models import Alarm, AlarmType, Severity


DEFAULT_SEVERITY: dict[AlarmType, Severity] = {
    AlarmType.UNKNOWN_SERVICE: Severity.WARNING,
    AlarmType.DESTRUCTIVE_ACTION_REQUESTED: Severity.CRITICAL,
    AlarmType.REMEDIATION_FAILED: Severity.CRITICAL,
    AlarmType.TURN_LIMIT_REACHED: Severity.WARNING,
    AlarmType.CONFIDENCE_LOW: Severity.INFO,
}


class AlarmManager:
    def __init__(self, severity_overrides: dict[str, str] | None = None):
        self.alarms: list[Alarm] = []
        self._overrides = severity_overrides or {}

    def _resolve_severity(self, alarm_type: AlarmType) -> Severity:
        if alarm_type.value in self._overrides:
            return Severity(self._overrides[alarm_type.value])
        return DEFAULT_SEVERITY[alarm_type]

    def emit(
        self,
        alarm_type: AlarmType,
        context: dict | None = None,
        recommended_action: str = "",
    ) -> bool:
        """
        Create and store an alarm. Returns True if the loop should halt (CRITICAL).
        """
        severity = self._resolve_severity(alarm_type)
        alarm = Alarm(
            type=alarm_type,
            context=context or {},
            severity=severity,
            recommended_action=recommended_action,
        )
        self.alarms.append(alarm)
        return severity == Severity.CRITICAL

    def get_alarms(self) -> list[Alarm]:
        return list(self.alarms)

    def has_critical(self) -> bool:
        return any(a.severity == Severity.CRITICAL for a in self.alarms)

    def clear(self) -> None:
        self.alarms.clear()
