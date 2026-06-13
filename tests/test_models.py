import json
import pytest
from pydantic import ValidationError

from src.harness.models import (
    Alert,
    AgentResponse,
    Alarm,
    AlarmType,
    CheckpointResult,
    CheckpointStage,
    GuardrailDecision,
    RunStatus,
    Severity,
    ToolCall,
)
from src.agents.base import BaseAgent


# --- Enum completeness ---

def test_severity_values():
    assert set(Severity) == {"INFO", "WARNING", "CRITICAL"}


def test_alarm_type_values():
    assert set(AlarmType) == {
        "UNKNOWN_SERVICE",
        "DESTRUCTIVE_ACTION_REQUESTED",
        "REMEDIATION_FAILED",
        "TURN_LIMIT_REACHED",
        "CONFIDENCE_LOW",
    }


def test_checkpoint_stage_values():
    assert set(CheckpointStage) == {
        "CP1_ALERT_PARSED",
        "CP2_HYPOTHESIS_FORMED",
        "CP3_PLAN_VALIDATED",
        "CP4_HEALTH_CHECK",
    }


def test_run_status_values():
    assert set(RunStatus) == {
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "ESCALATED",
        "AWAITING_HUMAN",
    }


def test_guardrail_decision_values():
    assert set(GuardrailDecision) == {"ALLOWED", "BLOCKED", "NEEDS_APPROVAL"}


# --- Alert validation ---

def test_alert_requires_service():
    with pytest.raises(ValidationError):
        Alert(severity="WARNING", description="disk full")


def test_alert_requires_severity():
    with pytest.raises(ValidationError):
        Alert(service="api", description="disk full")


def test_alert_requires_description():
    with pytest.raises(ValidationError):
        Alert(service="api", severity="WARNING")


def test_alert_auto_generates_id_and_timestamp():
    a = Alert(service="api", severity="WARNING", description="disk full")
    assert a.alert_id is not None
    assert a.timestamp is not None


def test_alert_two_instances_have_different_ids():
    a1 = Alert(service="api", severity="WARNING", description="disk full")
    a2 = Alert(service="api", severity="WARNING", description="disk full")
    assert a1.alert_id != a2.alert_id


# --- AgentResponse defaults ---

def test_agent_response_empty_tool_calls():
    r = AgentResponse()
    assert r.tool_calls == []
    assert r.tool_calls is not None


# --- BaseAgent is abstract ---

def test_base_agent_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseAgent()  # type: ignore[abstract]


# --- CheckpointResult serialization ---

def test_checkpoint_result_round_trips_json():
    cp = CheckpointResult(
        run_id="run-1",
        stage=CheckpointStage.CP1_ALERT_PARSED,
        passed=True,
        state={"key": "value"},
    )
    data = cp.model_dump_json()
    restored = CheckpointResult.model_validate_json(data)
    assert restored.run_id == cp.run_id
    assert restored.stage == cp.stage
    assert restored.passed == cp.passed
    assert restored.state == cp.state
    assert restored.checkpoint_id == cp.checkpoint_id


# --- Alarm serialization ---

def test_alarm_serializes_all_fields():
    alarm = Alarm(
        type=AlarmType.CONFIDENCE_LOW,
        severity=Severity.INFO,
        recommended_action="review logs",
    )
    data = json.loads(alarm.model_dump_json())
    assert "alarm_id" in data
    assert "type" in data
    assert "context" in data
    assert "severity" in data
    assert "recommended_action" in data
    assert "timestamp" in data
