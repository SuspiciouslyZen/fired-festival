# U1. Shared Models and BaseAgent

## Dependencies

- [[u00-project-setup]] — repo skeleton, `pyproject.toml`, all `__init__.py` files

**Files created by this unit:**
- `src/harness/models.py`
- `src/agents/base.py`
- `tests/test_models.py`

---

## File: `src/harness/models.py`

Every data type the harness uses. Other modules import from here — this file imports from nothing in `src/`.

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlarmType(StrEnum):
    UNKNOWN_SERVICE = "UNKNOWN_SERVICE"
    DESTRUCTIVE_ACTION_REQUESTED = "DESTRUCTIVE_ACTION_REQUESTED"
    REMEDIATION_FAILED = "REMEDIATION_FAILED"
    TURN_LIMIT_REACHED = "TURN_LIMIT_REACHED"
    CONFIDENCE_LOW = "CONFIDENCE_LOW"


class CheckpointStage(StrEnum):
    CP1_ALERT_PARSED = "CP1_ALERT_PARSED"
    CP2_HYPOTHESIS_FORMED = "CP2_HYPOTHESIS_FORMED"
    CP3_PLAN_VALIDATED = "CP3_PLAN_VALIDATED"
    CP4_HEALTH_CHECK = "CP4_HEALTH_CHECK"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    AWAITING_HUMAN = "AWAITING_HUMAN"


class GuardrailDecision(StrEnum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"


# --- Input/Output Material ---

class Alert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    service: str
    severity: str
    description: str
    source: str = "manual"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AgentResponse(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = Field(default_factory=dict)


class Alarm(BaseModel):
    alarm_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: AlarmType
    context: dict[str, Any] = Field(default_factory=dict)
    severity: Severity
    recommended_action: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CheckpointResult(BaseModel):
    checkpoint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    stage: CheckpointStage
    passed: bool
    state: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RemediationReport(BaseModel):
    run_id: str
    alert: Alert
    diagnosis: str
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    metrics_before: dict[str, Any] = Field(default_factory=dict)
    metrics_after: dict[str, Any] = Field(default_factory=dict)
    downstream_effects: list[str] = Field(default_factory=list)
    resolution_status: str = "resolved"
    alarms: list[Alarm] = Field(default_factory=list)
    checkpoints: list[CheckpointResult] = Field(default_factory=list)


class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    alert_id: str
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    result: RemediationReport | None = None


class EscalationDecision(BaseModel):
    decision: str  # "approve", "reject", "override"
    reason: str = ""
    override_action: str | None = None
```

---

## File: `src/agents/base.py`

```python
from abc import ABC, abstractmethod

from src.harness.models import AgentResponse


class BaseAgent(ABC):
    @abstractmethod
    async def run(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AgentResponse:
        """Call the LLM with messages and tool definitions. Return structured response."""
        ...

    @abstractmethod
    def supports_tools(self) -> bool:
        """Whether this agent supports tool calling."""
        ...
```

---

## Tests: `tests/test_models.py`

Test that:
- Every Pydantic model validates correct input and rejects missing required fields
- `Alert` requires `service`, `severity`, `description` — reject if any missing
- `Alert` generates `alert_id` and `timestamp` automatically if omitted
- All enums contain their expected values (list them explicitly in the test)
- `BaseAgent` cannot be instantiated (raises `TypeError`)
- `AgentResponse` with no tool_calls has empty list, not None
- `CheckpointResult` serializes to JSON and back without data loss
- `Alarm` serializes to JSON with all fields present
