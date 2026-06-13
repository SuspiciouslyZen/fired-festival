import json
import pytest

from src.harness.material import MaterialHandler
from src.harness.models import Alert, Alarm, AlarmType, CheckpointResult, CheckpointStage, Severity


# 1. Valid alert validates successfully
def test_validate_alert_valid():
    alert = MaterialHandler.validate_alert({"service": "web-api", "severity": "high", "description": "latency spike"})
    assert isinstance(alert, Alert)
    assert alert.service == "web-api"


# 2. Missing service → ValueError
def test_validate_alert_missing_service():
    with pytest.raises(ValueError, match="Invalid alert"):
        MaterialHandler.validate_alert({"severity": "high", "description": "latency spike"})


# 3. Missing severity → ValueError
def test_validate_alert_missing_severity():
    with pytest.raises(ValueError, match="Invalid alert"):
        MaterialHandler.validate_alert({"service": "web-api", "description": "latency spike"})


# 4. Missing description → ValueError
def test_validate_alert_missing_description():
    with pytest.raises(ValueError, match="Invalid alert"):
        MaterialHandler.validate_alert({"service": "web-api", "severity": "high"})


# 5. Extra fields in metadata preserved
def test_validate_alert_metadata_preserved():
    alert = MaterialHandler.validate_alert({
        "service": "web-api",
        "severity": "high",
        "description": "latency spike",
        "metadata": {"region": "us-east-1", "host": "prod-1"},
    })
    assert alert.metadata["region"] == "us-east-1"
    assert alert.metadata["host"] == "prod-1"


# 6. build_report returns complete report
def test_build_report_complete():
    alert = Alert(service="redis", severity="critical", description="OOM")
    alarm = Alarm(type=AlarmType.REMEDIATION_FAILED, severity=Severity.CRITICAL, recommended_action="escalate")
    cp = CheckpointResult(run_id="run-1", stage=CheckpointStage.CP1_ALERT_PARSED, passed=True)

    report = MaterialHandler.build_report(
        run_id="run-1",
        alert=alert,
        diagnosis="Redis ran out of memory",
        actions_taken=[{"action": "restart_service", "target": "redis"}],
        outcomes=["service restarted"],
        metrics_before={"memory_pct": 99},
        metrics_after={"memory_pct": 45},
        downstream_effects=["cache cleared"],
        resolution_status="resolved",
        alarms=[alarm],
        checkpoints=[cp],
    )

    assert report.run_id == "run-1"
    assert report.alert.service == "redis"
    assert report.diagnosis == "Redis ran out of memory"
    assert len(report.actions_taken) == 1
    assert len(report.alarms) == 1
    assert len(report.checkpoints) == 1


# 7. Report serializes round-trip without data loss
def test_build_report_json_roundtrip():
    alert = Alert(service="postgres", severity="high", description="slow queries")
    report = MaterialHandler.build_report(
        run_id="run-2",
        alert=alert,
        diagnosis="missing index",
        actions_taken=[],
        outcomes=[],
        metrics_before={},
        metrics_after={},
        downstream_effects=[],
        resolution_status="resolved",
        alarms=[],
        checkpoints=[],
    )

    data = report.model_dump_json()
    restored = type(report).model_validate_json(data)
    assert restored.run_id == report.run_id
    assert restored.alert.service == report.alert.service
    assert restored.diagnosis == report.diagnosis
