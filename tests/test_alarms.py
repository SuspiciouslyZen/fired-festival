import json
import pytest

from src.harness.alarms import AlarmManager
from src.harness.models import AlarmType, Severity


@pytest.fixture
def manager():
    return AlarmManager()


# 1. WARNING alarm → no halt
def test_warning_no_halt(manager):
    assert manager.emit(AlarmType.UNKNOWN_SERVICE) is False


# 2. CRITICAL alarm → halt
def test_critical_halts(manager):
    assert manager.emit(AlarmType.DESTRUCTIVE_ACTION_REQUESTED) is True


# 3. INFO alarm → no halt
def test_info_no_halt(manager):
    assert manager.emit(AlarmType.CONFIDENCE_LOW) is False


# 4. DESTRUCTIVE_ACTION_REQUESTED defaults to CRITICAL
def test_destructive_action_is_critical(manager):
    manager.emit(AlarmType.DESTRUCTIVE_ACTION_REQUESTED)
    assert manager.get_alarms()[0].severity == Severity.CRITICAL


# 5. UNKNOWN_SERVICE defaults to WARNING
def test_unknown_service_is_warning(manager):
    manager.emit(AlarmType.UNKNOWN_SERVICE)
    assert manager.get_alarms()[0].severity == Severity.WARNING


# 6. CONFIDENCE_LOW defaults to INFO
def test_confidence_low_is_info(manager):
    manager.emit(AlarmType.CONFIDENCE_LOW)
    assert manager.get_alarms()[0].severity == Severity.INFO


# 7. Multiple emits accumulate
def test_multiple_emits_accumulate(manager):
    manager.emit(AlarmType.CONFIDENCE_LOW)
    manager.emit(AlarmType.UNKNOWN_SERVICE)
    manager.emit(AlarmType.REMEDIATION_FAILED)
    assert len(manager.get_alarms()) == 3


# 8. Alarm serializes to JSON with all required fields
def test_alarm_json_fields(manager):
    manager.emit(AlarmType.TURN_LIMIT_REACHED, context={"turn": 15}, recommended_action="escalate")
    alarm = manager.get_alarms()[0]
    data = json.loads(alarm.model_dump_json())
    for field in ("alarm_id", "type", "context", "severity", "recommended_action", "timestamp"):
        assert field in data


# 9. Severity override: UNKNOWN_SERVICE → CRITICAL, emit returns True
def test_severity_override_unknown_service():
    mgr = AlarmManager(severity_overrides={"UNKNOWN_SERVICE": "CRITICAL"})
    assert mgr.emit(AlarmType.UNKNOWN_SERVICE) is True
    assert mgr.get_alarms()[0].severity == Severity.CRITICAL


# 10. has_critical() False when only warnings
def test_has_critical_false_with_only_warnings(manager):
    manager.emit(AlarmType.UNKNOWN_SERVICE)
    manager.emit(AlarmType.TURN_LIMIT_REACHED)
    assert manager.has_critical() is False


# 11. clear() empties alarm list
def test_clear_empties_alarms(manager):
    manager.emit(AlarmType.CONFIDENCE_LOW)
    manager.emit(AlarmType.UNKNOWN_SERVICE)
    manager.clear()
    assert manager.get_alarms() == []
