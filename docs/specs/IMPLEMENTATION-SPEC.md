# Ops Runbook Harness — Implementation Specification

> This document is the single source of truth for building the harness.
> Each unit is self-contained. Build them in order. Follow the specs exactly.

---

## Repo Structure (Final State)

```
fired-festival/
├── docs/                           # Planning, research, architecture docs
│   ├── plans/
│   ├── specs/                      # This file lives here
│   └── architecture/               # Move architecture HTML/PDF here
├── src/                            # All harness source code
│   ├── harness/
│   │   ├── __init__.py
│   │   ├── loop.py                 # U7: Core agent loop
│   │   ├── guardrails.py           # U2: Guardrail loading + enforcement
│   │   ├── checkpoints.py          # U4: Checkpoint evaluation + persistence
│   │   ├── material.py             # U5: Input/output schema validation
│   │   ├── alarms.py               # U3: Alarm types + emission
│   │   └── models.py               # U1: Shared Pydantic models
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                 # U1: BaseAgent abstract class
│   │   ├── claude_agent.py         # U8: Claude implementation
│   │   └── openai_agent.py         # U8: OpenAI swap implementation
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py             # U6: Tool registration + allow-list check
│   │   ├── check_status.py         # U6: Mock tool
│   │   ├── restart_service.py      # U6: Mock tool
│   │   ├── read_logs.py            # U6: Mock tool
│   │   ├── kill_query.py           # U6: Mock tool
│   │   └── flush_dns.py            # U6: Mock tool
│   ├── db/
│   │   ├── __init__.py
│   │   └── store.py                # U4: SQLite checkpoint store
│   └── api/
│       ├── __init__.py
│       └── routes.py               # U9: FastAPI endpoints
├── tests/
│   ├── __init__.py
│   ├── test_models.py              # U1
│   ├── test_guardrails.py          # U2
│   ├── test_alarms.py              # U3
│   ├── test_checkpoints.py         # U4
│   ├── test_material.py            # U5
│   ├── test_tools.py               # U6
│   ├── test_loop.py                # U7
│   ├── test_agents.py              # U8
│   └── test_api.py                 # U9
├── fixtures/
│   ├── alerts/                     # Sample alert JSONs for demo + tests
│   │   ├── high_cpu_web_api.json
│   │   ├── hung_query_postgres.json
│   │   ├── dns_failure_cdn.json
│   │   └── unknown_service.json
│   └── mock_responses/             # Deterministic tool responses per scenario
│       ├── high_cpu_scenario.py
│       ├── hung_query_scenario.py
│       ├── dns_failure_scenario.py
│       └── unknown_service_scenario.py
├── guardrails.yaml                 # Declared guardrail config (root level, visible)
├── main.py                         # Entry point
├── pyproject.toml
├── Dockerfile
├── CLAUDE.md
├── HARNESS.md                      # Architecture doc (deliverable)
├── README.md
├── RESEARCH.md
└── STRATEGY.md
```

---

## CLAUDE.md (write this file first)

```markdown
# Ops Runbook Harness

## Build & Run

- Python 3.12+
- Install: `pip install -e ".[dev]"`
- Run server: `python main.py` (starts uvicorn on port 8000)
- Run tests: `pytest tests/ -v`
- Run single test file: `pytest tests/test_guardrails.py -v`
- Type check: `pyright src/`

## Project layout

- `src/` — all source code. Four harness pillars in `src/harness/`, agents in `src/agents/`, tools in `src/tools/`
- `tests/` — pytest tests, one file per module
- `fixtures/` — sample alert JSONs and mock tool responses
- `guardrails.yaml` — declared guardrail config (root level for visibility)

## Conventions

- All data models are Pydantic v2 in `src/harness/models.py`
- Enums use Python `StrEnum` (Python 3.11+)
- Each pillar module exposes a manager class (e.g., `GuardrailEngine`, `CheckpointManager`, `AlarmManager`)
- Tools are registered via `ToolRegistry` — never called directly by the agent
- Agent implementations go in `src/agents/` and must subclass `BaseAgent`
- SQLite database file: `data/harness.db` (auto-created)
- Tests use pytest with no external dependencies (mock LLM calls)
- Import paths: `from src.harness.models import Alert` etc.
```

---

## U0. Project Setup (pyproject.toml, CLAUDE.md, guardrails.yaml, repo restructure)

### pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ops-runbook-harness"
version = "0.1.0"
description = "AI agent harness for infrastructure incident remediation"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "anthropic>=0.52.0",
    "openai>=1.82.0",
    "pydantic>=2.11.0",
    "pyyaml>=6.0.2",
    "aiosqlite>=0.20.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
    "pyright>=1.1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.pyright]
pythonVersion = "3.12"
include = ["src"]
```

### guardrails.yaml

```yaml
allowed_actions:
  - check_status
  - restart_service
  - read_logs
  - kill_query
  - flush_dns

environment_scope: staging

production_requires_approval: true

max_turns: 15
token_budget: 50000
timeout_seconds: 120

requires_approval:
  - restart_service
  - kill_query

severity_overrides:
  DESTRUCTIVE_ACTION_REQUESTED: CRITICAL
  UNKNOWN_SERVICE: WARNING
  REMEDIATION_FAILED: CRITICAL
  TURN_LIMIT_REACHED: WARNING
  CONFIDENCE_LOW: INFO
```

### main.py

```python
import uvicorn
from src.api.routes import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Repo restructure commands

```bash
mkdir -p docs/architecture
mv architecture-1-page.html docs/architecture/
mv architecture-1-page.pdf docs/architecture/
mv architecture.html docs/architecture/
mv architecture-doc-template.html docs/architecture/
mv "24-hour Build Challenge.pdf" docs/
mkdir -p src/harness src/agents src/tools src/db src/api
mkdir -p tests fixtures/alerts fixtures/mock_responses
touch src/__init__.py src/harness/__init__.py src/agents/__init__.py
touch src/tools/__init__.py src/db/__init__.py src/api/__init__.py
touch tests/__init__.py
mkdir -p data
```

---

## U1. Shared Models and BaseAgent

### File: `src/harness/models.py`

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

### File: `src/agents/base.py`

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

### Tests: `tests/test_models.py`

Test that:
- Every Pydantic model validates correct input and rejects missing required fields
- `Alert` requires `service`, `severity`, `description` — reject if any missing
- `Alert` generates `alert_id` and `timestamp` automatically if omitted
- All enums contain their expected values (list them explicitly in the test)
- `BaseAgent` cannot be instantiated (raises `TypeError`)
- `AgentResponse` with no tool_calls has empty list, not None
- `CheckpointResult` serializes to JSON and back without data loss
- `Alarm` serializes to JSON with all fields present

---

## U2. Guardrails Module

### File: `src/harness/guardrails.py`

```python
"""
Guardrail loading and enforcement.

Loads guardrails from YAML config file. Exposes:
- GuardrailConfig: Pydantic model of the YAML
- GuardrailEngine: stateless checker

The engine is initialized once with the config. The loop calls
check_action() before every tool execution and check_limits()
every turn.
"""
from pathlib import Path
import yaml
from pydantic import BaseModel
from src.harness.models import GuardrailDecision


class GuardrailConfig(BaseModel):
    allowed_actions: list[str]
    environment_scope: str = "staging"
    production_requires_approval: bool = True
    max_turns: int = 15
    token_budget: int = 50000
    timeout_seconds: int = 120
    requires_approval: list[str] = []
    severity_overrides: dict[str, str] = {}


class GuardrailEngine:
    def __init__(self, config: GuardrailConfig):
        self.config = config

    @classmethod
    def from_yaml(cls, path: str | Path) -> "GuardrailEngine":
        """Load guardrails from a YAML file. Raise ValueError on invalid YAML."""
        path = Path(path)
        with path.open() as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid guardrails YAML: expected mapping, got {type(raw).__name__}")
        config = GuardrailConfig(**raw)
        return cls(config)

    def check_action(self, action_name: str, environment: str | None = None) -> GuardrailDecision:
        """
        Check if an action is allowed.
        - Not on allowed_actions list → BLOCKED
        - On requires_approval list → NEEDS_APPROVAL
        - Environment is production and production_requires_approval → NEEDS_APPROVAL
        - Otherwise → ALLOWED
        """
        env = environment or self.config.environment_scope

        if action_name not in self.config.allowed_actions:
            return GuardrailDecision.BLOCKED

        if env == "production" and self.config.production_requires_approval:
            return GuardrailDecision.NEEDS_APPROVAL

        if action_name in self.config.requires_approval:
            return GuardrailDecision.NEEDS_APPROVAL

        return GuardrailDecision.ALLOWED

    def check_limits(self, turn_count: int, token_count: int) -> tuple[bool, str | None]:
        """
        Check turn and token limits.
        Returns (within_limits: bool, violation_reason: str | None).
        """
        if turn_count >= self.config.max_turns:
            return False, f"Turn limit exceeded: {turn_count}/{self.config.max_turns}"
        if token_count >= self.config.token_budget:
            return False, f"Token budget exceeded: {token_count}/{self.config.token_budget}"
        return True, None
```

### Tests: `tests/test_guardrails.py`

Write tests for ALL of these scenarios:
1. `check_action("check_status")` in staging → `ALLOWED`
2. `check_action("delete_database")` → `BLOCKED` (not on allow-list)
3. `check_action("restart_service")` in staging → `NEEDS_APPROVAL` (on requires_approval list)
4. `check_action("check_status", environment="production")` → `NEEDS_APPROVAL`
5. `check_limits(14, 100)` → `(True, None)`
6. `check_limits(15, 100)` → `(False, "Turn limit exceeded...")`
7. `check_limits(1, 50000)` → `(False, "Token budget exceeded...")`
8. `from_yaml` with valid file loads correctly
9. `from_yaml` with malformed YAML raises `ValueError`
10. Empty `allowed_actions: []` blocks all actions

Use a pytest fixture that writes a temporary YAML file for tests 8-10.

---

## U3. Alarms Module

### File: `src/harness/alarms.py`

```python
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
```

### Tests: `tests/test_alarms.py`

1. Emit `WARNING` alarm → returns `False` (no halt)
2. Emit `CRITICAL` alarm → returns `True` (halt)
3. Emit `INFO` alarm → returns `False`
4. `DESTRUCTIVE_ACTION_REQUESTED` defaults to `CRITICAL`
5. `UNKNOWN_SERVICE` defaults to `WARNING`
6. `CONFIDENCE_LOW` defaults to `INFO`
7. Multiple emits accumulate — `get_alarms()` returns all
8. Alarm serializes to JSON with all fields: `type`, `context`, `severity`, `recommended_action`, `timestamp`, `alarm_id`
9. Severity override changes `UNKNOWN_SERVICE` to `CRITICAL` → emit returns `True`
10. `has_critical()` returns `False` when only warnings exist
11. `clear()` empties the alarm list

---

## U4. Checkpoint Module + SQLite Store

### File: `src/db/store.py`

```python
"""
SQLite checkpoint and run persistence.

Uses aiosqlite for async access. Database is created automatically
on first use. Schema has two tables: runs and checkpoints.

All methods are async. The store is initialized with a database path
and creates the schema on connect().
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    result_json TEXT
);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    passed INTEGER NOT NULL,
    state_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_run_id ON checkpoints(run_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_stage ON checkpoints(run_id, stage);
"""


class CheckpointStore:
    def __init__(self, db_path: str = "data/harness.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Store not connected. Call connect() first.")
        return self._db

    async def create_run(self, run_id: str, alert_id: str) -> None:
        await self.db.execute(
            "INSERT INTO runs (run_id, alert_id, status, started_at) VALUES (?, ?, ?, ?)",
            (run_id, alert_id, "RUNNING", datetime.now(timezone.utc).isoformat()),
        )
        await self.db.commit()

    async def update_run_status(self, run_id: str, status: str, result_json: str | None = None) -> None:
        completed = datetime.now(timezone.utc).isoformat() if status != "RUNNING" else None
        await self.db.execute(
            "UPDATE runs SET status = ?, completed_at = ?, result_json = ? WHERE run_id = ?",
            (status, completed, result_json, run_id),
        )
        await self.db.commit()

    async def save_checkpoint(
        self,
        checkpoint_id: str,
        run_id: str,
        stage: str,
        passed: bool,
        state: dict,
        failure_reason: str | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO checkpoints (checkpoint_id, run_id, stage, passed, state_json, failure_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (checkpoint_id, run_id, stage, int(passed), json.dumps(state), failure_reason, datetime.now(timezone.utc).isoformat()),
        )
        await self.db.commit()

    async def get_checkpoints(self, run_id: str) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT checkpoint_id, run_id, stage, passed, state_json, failure_reason, created_at FROM checkpoints WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "checkpoint_id": r[0], "run_id": r[1], "stage": r[2],
                "passed": bool(r[3]), "state": json.loads(r[4]),
                "failure_reason": r[5], "created_at": r[6],
            }
            for r in rows
        ]

    async def get_checkpoint_state(self, run_id: str, stage: str) -> dict | None:
        """Load saved state for a specific checkpoint. Used for replay."""
        cursor = await self.db.execute(
            "SELECT state_json FROM checkpoints WHERE run_id = ? AND stage = ? AND passed = 1 ORDER BY created_at DESC LIMIT 1",
            (run_id, stage),
        )
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def get_run(self, run_id: str) -> dict | None:
        cursor = await self.db.execute(
            "SELECT run_id, alert_id, status, started_at, completed_at, result_json FROM runs WHERE run_id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "run_id": row[0], "alert_id": row[1], "status": row[2],
            "started_at": row[3], "completed_at": row[4],
            "result": json.loads(row[5]) if row[5] else None,
        }
```

### File: `src/harness/checkpoints.py`

```python
"""
Checkpoint evaluation.

CheckpointManager evaluates each checkpoint stage against its criteria.
It uses CheckpointStore for persistence. Each checkpoint receives the
current run state and returns a CheckpointResult.

Checkpoint criteria:
- CP1: Alert parsed — service and severity are known/valid
- CP2: Hypothesis formed — agent provided diagnosis with confidence > threshold
- CP3: Plan valid — all proposed actions are on the guardrail allow-list
- CP4: Health check — post-action status shows improvement

The manager also supports loading state from a prior run for replay.
"""
from src.harness.models import CheckpointResult, CheckpointStage, GuardrailDecision
from src.harness.guardrails import GuardrailEngine
from src.db.store import CheckpointStore

KNOWN_SERVICES = ["web-api", "postgres", "redis", "cdn", "worker", "gateway"]


class CheckpointManager:
    def __init__(self, store: CheckpointStore, guardrail_engine: GuardrailEngine):
        self.store = store
        self.guardrails = guardrail_engine
        self.results: list[CheckpointResult] = []

    async def evaluate_cp1(self, run_id: str, alert_data: dict) -> CheckpointResult:
        """CP1: Alert parsed. Pass if service is known and severity is valid."""
        service = alert_data.get("service", "")
        severity = alert_data.get("severity", "")
        valid_severities = ["low", "medium", "high", "critical"]

        passed = service in KNOWN_SERVICES and severity.lower() in valid_severities
        failure_reason = None
        if not passed:
            reasons = []
            if service not in KNOWN_SERVICES:
                reasons.append(f"Unknown service: {service}")
            if severity.lower() not in valid_severities:
                reasons.append(f"Invalid severity: {severity}")
            failure_reason = "; ".join(reasons)

        result = CheckpointResult(
            run_id=run_id,
            stage=CheckpointStage.CP1_ALERT_PARSED,
            passed=passed,
            state={"service": service, "severity": severity, "alert": alert_data},
            failure_reason=failure_reason,
        )
        await self._persist(result)
        return result

    async def evaluate_cp2(self, run_id: str, diagnosis: dict) -> CheckpointResult:
        """CP2: Hypothesis formed. Pass if confidence > 0.6 and hypothesis is non-empty."""
        confidence = diagnosis.get("confidence", 0.0)
        hypothesis = diagnosis.get("hypothesis", "")
        threshold = 0.6

        passed = confidence >= threshold and len(hypothesis) > 0
        failure_reason = None
        if not passed:
            if confidence < threshold:
                failure_reason = f"Confidence too low: {confidence} < {threshold}"
            elif not hypothesis:
                failure_reason = "No hypothesis provided"

        result = CheckpointResult(
            run_id=run_id,
            stage=CheckpointStage.CP2_HYPOTHESIS_FORMED,
            passed=passed,
            state={"diagnosis": diagnosis, "confidence": confidence},
            failure_reason=failure_reason,
        )
        await self._persist(result)
        return result

    async def evaluate_cp3(self, run_id: str, planned_actions: list[str]) -> CheckpointResult:
        """CP3: Plan valid. Pass if ALL proposed actions are on the allow-list."""
        blocked = []
        for action in planned_actions:
            decision = self.guardrails.check_action(action)
            if decision == GuardrailDecision.BLOCKED:
                blocked.append(action)

        passed = len(blocked) == 0
        failure_reason = f"Blocked actions: {blocked}" if blocked else None

        result = CheckpointResult(
            run_id=run_id,
            stage=CheckpointStage.CP3_PLAN_VALIDATED,
            passed=passed,
            state={"planned_actions": planned_actions, "blocked": blocked},
            failure_reason=failure_reason,
        )
        await self._persist(result)
        return result

    async def evaluate_cp4(self, run_id: str, health_data: dict) -> CheckpointResult:
        """CP4: Health check. Pass if status is 'healthy' or metrics improved."""
        status = health_data.get("status", "unknown")
        passed = status in ("healthy", "recovered", "ok")
        failure_reason = None if passed else f"Service status: {status}"

        result = CheckpointResult(
            run_id=run_id,
            stage=CheckpointStage.CP4_HEALTH_CHECK,
            passed=passed,
            state={"health_data": health_data},
            failure_reason=failure_reason,
        )
        await self._persist(result)
        return result

    async def load_replay_state(self, run_id: str, stage: CheckpointStage) -> dict | None:
        """Load saved state from a prior run for replay."""
        return await self.store.get_checkpoint_state(run_id, stage.value)

    async def _persist(self, result: CheckpointResult) -> None:
        self.results.append(result)
        await self.store.save_checkpoint(
            checkpoint_id=result.checkpoint_id,
            run_id=result.run_id,
            stage=result.stage.value,
            passed=result.passed,
            state=result.state,
            failure_reason=result.failure_reason,
        )
```

### Tests: `tests/test_checkpoints.py`

Use an in-memory SQLite (pass `":memory:"` as db_path) or a tmp_path fixture.

1. CP1 pass: known service + valid severity → `passed=True`, state contains alert data
2. CP1 fail: unknown service → `passed=False`, failure_reason mentions the service
3. CP2 pass: confidence 0.8 + hypothesis → `passed=True`
4. CP2 fail: confidence 0.3 → `passed=False`, failure_reason mentions threshold
5. CP3 pass: all actions on allow-list → `passed=True`
6. CP3 fail: one blocked action → `passed=False`, failure_reason lists blocked action
7. CP4 pass: status "healthy" → `passed=True`
8. CP4 fail: status "degraded" → `passed=False`
9. Checkpoints are persisted to SQLite — `store.get_checkpoints(run_id)` returns them
10. Multiple runs are isolated — run A checkpoints not returned for run B
11. Replay: save CP1 state, load it back — state matches exactly
12. Database auto-creates on connect

---

## U5. Material Handling

### File: `src/harness/material.py`

```python
"""
Input/output schema validation for the harness.

Validates incoming alert JSON against the Alert model.
Structures outgoing remediation reports.

This module is deliberately thin — it's Pydantic validation
with clear error messages. The value is in the schema enforcement,
not complex logic.
"""
from src.harness.models import Alert, RemediationReport, Alarm, CheckpointResult


class MaterialHandler:
    @staticmethod
    def validate_alert(raw: dict) -> Alert:
        """
        Parse and validate an alert dict. Raises ValueError with
        clear field-level error messages on invalid input.
        """
        try:
            return Alert(**raw)
        except Exception as e:
            raise ValueError(f"Invalid alert: {e}") from e

    @staticmethod
    def build_report(
        run_id: str,
        alert: Alert,
        diagnosis: str,
        actions_taken: list[dict],
        outcomes: list[str],
        metrics_before: dict,
        metrics_after: dict,
        downstream_effects: list[str],
        resolution_status: str,
        alarms: list[Alarm],
        checkpoints: list[CheckpointResult],
    ) -> RemediationReport:
        return RemediationReport(
            run_id=run_id,
            alert=alert,
            diagnosis=diagnosis,
            actions_taken=actions_taken,
            outcomes=outcomes,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            downstream_effects=downstream_effects,
            resolution_status=resolution_status,
            alarms=alarms,
            checkpoints=checkpoints,
        )
```

### Tests: `tests/test_material.py`

1. Valid alert dict validates successfully
2. Missing `service` → `ValueError`
3. Missing `severity` → `ValueError`
4. Missing `description` → `ValueError`
5. Extra fields in metadata preserved
6. `build_report` returns complete report with all fields
7. Report serializes to JSON round-trip without data loss

---

## U6. Tool Registry and Mock Tools

### File: `src/tools/registry.py`

```python
"""
Tool registration, schema exposure, and allow-list enforcement.

The registry holds all available tools. The loop calls execute()
which checks guardrails BEFORE running the tool function.

Each tool is registered with:
- name: string identifier (matches guardrails.yaml allow-list)
- description: what the tool does (sent to the LLM)
- parameters: JSON Schema dict of the tool's parameters (sent to the LLM)
- executor: async callable(args_dict) -> dict
"""
from typing import Any, Callable, Awaitable

from src.harness.guardrails import GuardrailEngine
from src.harness.models import GuardrailDecision, ToolResult


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        executor: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.executor = executor

    def to_llm_schema(self) -> dict:
        """Return the schema dict sent to the LLM for tool calling."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self, guardrails: GuardrailEngine):
        self._tools: dict[str, ToolDefinition] = {}
        self._guardrails = guardrails

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool_schemas(self) -> list[dict]:
        """Return all tool schemas for the LLM."""
        return [t.to_llm_schema() for t in self._tools.values()]

    async def execute(self, tool_name: str, arguments: dict[str, Any], environment: str | None = None) -> ToolResult:
        """
        Execute a tool call. Checks guardrails first.
        Returns ToolResult — never raises on tool errors.
        """
        if tool_name not in self._tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        decision = self._guardrails.check_action(tool_name, environment)
        if decision == GuardrailDecision.BLOCKED:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Action blocked by guardrails: {tool_name} is not on the allowed actions list",
            )
        if decision == GuardrailDecision.NEEDS_APPROVAL:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Action requires human approval: {tool_name}",
                output={"needs_approval": True},
            )

        try:
            result_data = await self._tools[tool_name].executor(arguments)
            return ToolResult(tool_name=tool_name, success=True, output=result_data)
        except Exception as e:
            return ToolResult(tool_name=tool_name, success=False, error=str(e))
```

### Mock Tool Files

Each mock tool file exports a `ToolDefinition`. All executors are async functions returning dicts.

**`src/tools/check_status.py`**

```python
from src.tools.registry import ToolDefinition

SERVICE_STATUS = {
    "web-api": {"status": "degraded", "cpu_percent": 94.2, "memory_percent": 67.1, "uptime_hours": 142, "error_rate": 12.3, "p95_latency_ms": 2340},
    "postgres": {"status": "warning", "active_connections": 148, "max_connections": 150, "longest_query_seconds": 3847, "replication_lag_ms": 12},
    "redis": {"status": "healthy", "memory_used_mb": 1024, "hit_rate": 0.97, "connected_clients": 42},
    "cdn": {"status": "degraded", "dns_resolution_ms": 8500, "cache_hit_rate": 0.34, "error_rate": 28.7},
    "worker": {"status": "healthy", "queue_depth": 12, "processing_rate": 45.2},
    "gateway": {"status": "healthy", "requests_per_second": 1240, "error_rate": 0.1},
}


async def _execute(args: dict) -> dict:
    service = args.get("service", "unknown")
    if service in SERVICE_STATUS:
        return {"service": service, **SERVICE_STATUS[service]}
    return {"service": service, "status": "unknown", "error": f"Service '{service}' not found"}


definition = ToolDefinition(
    name="check_status",
    description="Check the current health status and metrics of a service",
    parameters={
        "service": {"type": "string", "description": "Name of the service to check (e.g., 'web-api', 'postgres')"}
    },
    executor=_execute,
)
```

**`src/tools/restart_service.py`**

```python
from src.tools.registry import ToolDefinition


async def _execute(args: dict) -> dict:
    service = args.get("service", "unknown")
    return {
        "service": service,
        "action": "restart",
        "result": "success",
        "message": f"Service '{service}' restarted successfully",
        "new_status": "healthy",
        "restart_duration_seconds": 4.2,
    }


definition = ToolDefinition(
    name="restart_service",
    description="Restart a service instance. This is a mutating action.",
    parameters={
        "service": {"type": "string", "description": "Name of the service to restart"}
    },
    executor=_execute,
)
```

**`src/tools/read_logs.py`**

```python
from src.tools.registry import ToolDefinition

SAMPLE_LOGS = {
    "web-api": [
        "2026-06-12T10:23:01Z ERROR [web-api] Request timeout after 30s - GET /api/v2/users",
        "2026-06-12T10:23:02Z ERROR [web-api] CPU throttling detected - container limit reached",
        "2026-06-12T10:23:05Z WARN  [web-api] Connection pool exhausted, queuing requests",
        "2026-06-12T10:23:08Z ERROR [web-api] Health check failed - response time 4200ms > threshold 1000ms",
        "2026-06-12T10:23:12Z INFO  [web-api] Auto-scaling triggered but max instances reached (8/8)",
    ],
    "postgres": [
        "2026-06-12T10:20:00Z WARN  [postgres] Long-running query detected: SELECT * FROM events JOIN... (running 3847s)",
        "2026-06-12T10:21:30Z ERROR [postgres] Connection pool near capacity: 148/150 active connections",
        "2026-06-12T10:22:00Z WARN  [postgres] Lock contention on table 'events' - 12 queries waiting",
        "2026-06-12T10:22:45Z INFO  [postgres] Replication lag stable at 12ms",
    ],
    "cdn": [
        "2026-06-12T10:15:00Z ERROR [cdn] DNS resolution timeout for edge-us-west-2.cdn.example.com",
        "2026-06-12T10:15:30Z ERROR [cdn] Cache miss rate spiked to 66% - possible DNS propagation issue",
        "2026-06-12T10:16:00Z WARN  [cdn] Fallback to origin for 28.7% of requests",
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
```

**`src/tools/kill_query.py`**

```python
from src.tools.registry import ToolDefinition


async def _execute(args: dict) -> dict:
    query_id = args.get("query_id", "unknown")
    return {
        "query_id": query_id,
        "action": "kill",
        "result": "success",
        "message": f"Query '{query_id}' terminated",
        "freed_connections": 12,
        "lock_released": True,
    }


definition = ToolDefinition(
    name="kill_query",
    description="Kill a long-running or hung database query. This is a mutating action.",
    parameters={
        "query_id": {"type": "string", "description": "The ID of the query to kill"},
    },
    executor=_execute,
)
```

**`src/tools/flush_dns.py`**

```python
from src.tools.registry import ToolDefinition


async def _execute(args: dict) -> dict:
    service = args.get("service", "unknown")
    return {
        "service": service,
        "action": "flush_dns",
        "result": "success",
        "message": f"DNS cache flushed for '{service}'",
        "dns_resolution_ms_after": 45,
        "propagation_status": "complete",
    }


definition = ToolDefinition(
    name="flush_dns",
    description="Flush DNS cache for a service to resolve DNS propagation issues",
    parameters={
        "service": {"type": "string", "description": "Name of the service with DNS issues"},
    },
    executor=_execute,
)
```

### File: `src/tools/__init__.py`

```python
"""Register all tools with the registry."""
from src.harness.guardrails import GuardrailEngine
from src.tools.registry import ToolRegistry
from src.tools import check_status, restart_service, read_logs, kill_query, flush_dns


def create_registry(guardrails: GuardrailEngine) -> ToolRegistry:
    registry = ToolRegistry(guardrails)
    registry.register(check_status.definition)
    registry.register(restart_service.definition)
    registry.register(read_logs.definition)
    registry.register(kill_query.definition)
    registry.register(flush_dns.definition)
    return registry
```

### Tests: `tests/test_tools.py`

1. Registered tool executes and returns `success=True` with output
2. Unknown tool returns `success=False` with error message
3. Blocked tool (not on allow-list) returns `success=False` with guardrail error — mock a guardrail engine that blocks it
4. Tool returning `NEEDS_APPROVAL` returns the approval-needed result
5. `check_status("web-api")` returns degraded status with CPU metrics
6. `check_status("unknown-svc")` returns unknown status
7. `read_logs("postgres")` returns log lines
8. `get_tool_schemas()` returns schemas for all registered tools
9. Tool executor that raises exception returns `success=False` without crashing
10. `create_registry()` creates registry with all 5 tools registered

---

## U7. Core Agent Loop

### File: `src/harness/loop.py`

This is the most complex module. It ties all four pillars together.

```python
"""
Core agent loop.

The loop drives an agent through the incident remediation workflow:
  1. Validate alert (CP1)
  2. Agent diagnoses (CP2)
  3. Agent plans remediation (CP3)
  4. Execute remediation + health check (CP4)

Each step checks guardrails before tool execution, evaluates checkpoints,
and emits alarms when things go wrong. The loop never imports agent-specific
code — it uses the BaseAgent interface.

Key behaviors:
- Blocked actions → DESTRUCTIVE_ACTION_REQUESTED alarm → halt
- Turn limit → TURN_LIMIT_REACHED alarm → halt
- CRITICAL alarm → AWAITING_HUMAN status → halt (HITL)
- CP failure → appropriate alarm → halt or continue based on severity
"""
import json
import uuid
from typing import Any

from src.agents.base import BaseAgent
from src.harness.alarms import AlarmManager
from src.harness.checkpoints import CheckpointManager
from src.harness.guardrails import GuardrailEngine
from src.harness.material import MaterialHandler
from src.harness.models import (
    AgentResponse,
    Alert,
    AlarmType,
    CheckpointStage,
    GuardrailDecision,
    RemediationReport,
    RunStatus,
    ToolCall,
)
from src.tools.registry import ToolRegistry
from src.db.store import CheckpointStore


SYSTEM_PROMPT = """You are an infrastructure operations agent. Your job is to diagnose and remediate service incidents using the tools available to you.

WORKFLOW:
1. DIAGNOSE: Use check_status and read_logs to understand the problem. Form a hypothesis about the root cause.
2. PLAN: Decide which remediation action to take. Only use tools that are available to you.
3. EXECUTE: Run the remediation action.
4. VERIFY: Use check_status again to confirm the fix worked.

RULES:
- Only use the tools provided. Do not suggest actions you cannot take.
- If a tool call is blocked, choose a different approach or escalate.
- Always verify your fix worked with a health check after remediation.
- Be concise in your reasoning.

When you have completed diagnosis, respond with a JSON block:
{"diagnosis": {"hypothesis": "...", "confidence": 0.0-1.0, "evidence": ["..."]}}

When you have a remediation plan, respond with a JSON block:
{"plan": {"actions": ["tool_name_1", "tool_name_2"], "rationale": "..."}}

When remediation is complete and verified, respond with a JSON block:
{"resolution": {"status": "resolved", "summary": "...", "actions_taken": [{"tool": "...", "result": "..."}]}}
"""


class HarnessLoop:
    def __init__(
        self,
        agent: BaseAgent,
        guardrails: GuardrailEngine,
        store: CheckpointStore,
        registry: ToolRegistry,
    ):
        self.agent = agent
        self.guardrails = guardrails
        self.store = store
        self.registry = registry
        self.alarm_manager = AlarmManager(
            severity_overrides=guardrails.config.severity_overrides
        )
        self.checkpoint_manager = CheckpointManager(store, guardrails)

    async def run(
        self,
        alert: Alert,
        replay_from: CheckpointStage | None = None,
        replay_run_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute the full harness loop for an alert.

        Returns a dict with:
        - run_id: str
        - status: RunStatus value
        - report: RemediationReport (if resolved) or None
        - alarms: list of Alarm dicts
        - checkpoints: list of CheckpointResult dicts
        - escalation: dict with alarm context (if AWAITING_HUMAN)
        """
        run_id = str(uuid.uuid4())
        await self.store.create_run(run_id, alert.alert_id)

        # ---- CP1: Validate alert ----
        if replay_from and replay_from != CheckpointStage.CP1_ALERT_PARSED and replay_run_id:
            cp1_state = await self.checkpoint_manager.load_replay_state(
                replay_run_id, CheckpointStage.CP1_ALERT_PARSED
            )
            if cp1_state is None:
                return await self._fail(run_id, "Replay failed: CP1 state not found")
        else:
            cp1 = await self.checkpoint_manager.evaluate_cp1(run_id, alert.model_dump())
            if not cp1.passed:
                should_halt = self.alarm_manager.emit(
                    AlarmType.UNKNOWN_SERVICE,
                    context={"alert": alert.model_dump(), "reason": cp1.failure_reason},
                    recommended_action="Escalate to on-call engineer — unknown service",
                )
                if should_halt:
                    return await self._escalate(run_id)
                return await self._fail(run_id, cp1.failure_reason or "CP1 failed")

        # ---- Agent diagnosis loop (CP2) ----
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"INCIDENT ALERT:\n{json.dumps(alert.model_dump(), indent=2, default=str)}"},
        ]
        tools = self.registry.get_tool_schemas()

        diagnosis = None
        plan = None
        actions_taken = []
        metrics_before = {}
        metrics_after = {}
        turn = 0
        total_tokens = 0

        while turn < self.guardrails.config.max_turns:
            turn += 1

            within_limits, violation = self.guardrails.check_limits(turn, total_tokens)
            if not within_limits:
                self.alarm_manager.emit(
                    AlarmType.TURN_LIMIT_REACHED,
                    context={"turn": turn, "tokens": total_tokens, "reason": violation},
                    recommended_action="Review agent progress and decide whether to continue",
                )
                return await self._fail(run_id, violation or "Limits exceeded")

            response = await self.agent.run(messages, tools)
            total_tokens += sum(response.usage.values())
            messages.append({"role": "assistant", "content": response.text or "", "tool_calls_made": [tc.model_dump() for tc in response.tool_calls]})

            # Process tool calls
            if response.tool_calls:
                for tc in response.tool_calls:
                    decision = self.guardrails.check_action(tc.tool_name)
                    if decision == GuardrailDecision.BLOCKED:
                        self.alarm_manager.emit(
                            AlarmType.DESTRUCTIVE_ACTION_REQUESTED,
                            context={"tool": tc.tool_name, "args": tc.arguments},
                            recommended_action=f"Action '{tc.tool_name}' is not on the approved list. Review and approve manually.",
                        )
                        return await self._escalate(run_id)

                    result = await self.registry.execute(tc.tool_name, tc.arguments)
                    actions_taken.append({"tool": tc.tool_name, "args": tc.arguments, "result": result.model_dump()})
                    messages.append({"role": "tool", "content": json.dumps(result.model_dump(), default=str), "tool_name": tc.tool_name})

                    # Capture metrics from check_status calls
                    if tc.tool_name == "check_status" and result.success:
                        if not metrics_before:
                            metrics_before = result.output
                        else:
                            metrics_after = result.output
                continue

            # Parse structured responses from agent text
            if response.text:
                parsed = self._extract_json(response.text)
                if parsed:
                    if "diagnosis" in parsed and diagnosis is None:
                        diagnosis = parsed["diagnosis"]
                        cp2 = await self.checkpoint_manager.evaluate_cp2(run_id, diagnosis)
                        if not cp2.passed:
                            self.alarm_manager.emit(
                                AlarmType.CONFIDENCE_LOW,
                                context={"diagnosis": diagnosis, "reason": cp2.failure_reason},
                                recommended_action="Agent confidence is low. Consider providing additional context.",
                            )
                            messages.append({"role": "user", "content": "Your confidence is too low. Please gather more evidence using the available tools before forming a diagnosis."})
                            continue

                    if "plan" in parsed and plan is None:
                        plan = parsed["plan"]
                        planned_actions = plan.get("actions", [])
                        cp3 = await self.checkpoint_manager.evaluate_cp3(run_id, planned_actions)
                        if not cp3.passed:
                            self.alarm_manager.emit(
                                AlarmType.DESTRUCTIVE_ACTION_REQUESTED,
                                context={"plan": plan, "blocked": cp3.state.get("blocked", [])},
                                recommended_action="Plan contains blocked actions. Review and approve manually.",
                            )
                            return await self._escalate(run_id)
                        messages.append({"role": "user", "content": "Plan approved. Execute the remediation actions now."})
                        continue

                    if "resolution" in parsed:
                        # ---- CP4: Health check ----
                        health_data = metrics_after if metrics_after else {"status": "healthy"}
                        cp4 = await self.checkpoint_manager.evaluate_cp4(run_id, health_data)
                        if not cp4.passed:
                            self.alarm_manager.emit(
                                AlarmType.REMEDIATION_FAILED,
                                context={"health": health_data, "reason": cp4.failure_reason},
                                recommended_action="Remediation did not restore service health. Escalate immediately.",
                            )
                            return await self._escalate(run_id)

                        resolution = parsed["resolution"]
                        report = MaterialHandler.build_report(
                            run_id=run_id,
                            alert=alert,
                            diagnosis=diagnosis.get("hypothesis", "") if diagnosis else "",
                            actions_taken=actions_taken,
                            outcomes=[resolution.get("summary", "Resolved")],
                            metrics_before=metrics_before,
                            metrics_after=metrics_after,
                            downstream_effects=[],
                            resolution_status=resolution.get("status", "resolved"),
                            alarms=self.alarm_manager.get_alarms(),
                            checkpoints=self.checkpoint_manager.results,
                        )
                        await self.store.update_run_status(run_id, RunStatus.COMPLETED.value, report.model_dump_json())
                        return {
                            "run_id": run_id,
                            "status": RunStatus.COMPLETED.value,
                            "report": report.model_dump(),
                            "alarms": [a.model_dump() for a in self.alarm_manager.get_alarms()],
                            "checkpoints": [c.model_dump() for c in self.checkpoint_manager.results],
                        }

            # If agent returned text but no structured output and no tool calls, prompt it
            if not response.tool_calls:
                messages.append({"role": "user", "content": "Please continue with your diagnosis using the available tools, or provide your findings in the required JSON format."})

        # Fell through — turn limit
        self.alarm_manager.emit(
            AlarmType.TURN_LIMIT_REACHED,
            context={"turn": turn, "tokens": total_tokens},
            recommended_action="Agent did not resolve within turn limit",
        )
        return await self._fail(run_id, "Turn limit reached")

    async def _fail(self, run_id: str, reason: str) -> dict:
        await self.store.update_run_status(run_id, RunStatus.FAILED.value)
        return {
            "run_id": run_id,
            "status": RunStatus.FAILED.value,
            "error": reason,
            "alarms": [a.model_dump() for a in self.alarm_manager.get_alarms()],
            "checkpoints": [c.model_dump() for c in self.checkpoint_manager.results],
        }

    async def _escalate(self, run_id: str) -> dict:
        await self.store.update_run_status(run_id, RunStatus.AWAITING_HUMAN.value)
        critical_alarms = [a for a in self.alarm_manager.get_alarms() if a.severity.value == "CRITICAL"]
        return {
            "run_id": run_id,
            "status": RunStatus.AWAITING_HUMAN.value,
            "escalation": {
                "reason": critical_alarms[-1].recommended_action if critical_alarms else "Unknown",
                "alarm": critical_alarms[-1].model_dump() if critical_alarms else None,
            },
            "alarms": [a.model_dump() for a in self.alarm_manager.get_alarms()],
            "checkpoints": [c.model_dump() for c in self.checkpoint_manager.results],
        }

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract the first JSON object from agent text."""
        import re
        # Try to find JSON in code blocks first
        code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except json.JSONDecodeError:
                pass
        # Try to find bare JSON
        brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass
        return None
```

### Tests: `tests/test_loop.py`

Create a `MockAgent` class that implements `BaseAgent` and returns scripted responses:

```python
class MockAgent(BaseAgent):
    """Agent that returns pre-scripted responses in sequence."""
    def __init__(self, responses: list[AgentResponse]):
        self._responses = list(responses)
        self._call_count = 0

    async def run(self, messages, tools) -> AgentResponse:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return AgentResponse(text="I don't know what to do next.")

    def supports_tools(self) -> bool:
        return True
```

Test scenarios:

1. **Happy path**: Agent checks status → diagnoses → plans → executes → verifies → resolves. All 4 checkpoints pass. Status is COMPLETED. Report is returned.
2. **Blocked action**: Agent requests `delete_database` (not on allow-list) → DESTRUCTIVE_ACTION_REQUESTED alarm → status AWAITING_HUMAN.
3. **Turn limit**: Agent returns empty text for 15 turns → TURN_LIMIT_REACHED alarm → status FAILED.
4. **Low confidence**: Agent returns diagnosis with confidence 0.3 → CONFIDENCE_LOW alarm → agent is told to gather more evidence.
5. **CP4 failure**: Agent resolves but health check shows "degraded" → REMEDIATION_FAILED alarm → status AWAITING_HUMAN.
6. **JSON extraction**: `_extract_json` correctly parses JSON from code blocks and bare text.

---

## U8. Agent Implementations

### File: `src/agents/claude_agent.py`

```python
"""Claude agent using the Anthropic SDK with tool use."""
import os
from anthropic import AsyncAnthropic

from src.agents.base import BaseAgent
from src.harness.models import AgentResponse, ToolCall


class ClaudeAgent(BaseAgent):
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def run(self, messages: list[dict], tools: list[dict]) -> AgentResponse:
        # Convert messages to Anthropic format
        system_msg = ""
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            elif msg["role"] == "assistant":
                api_messages.append({"role": "assistant", "content": msg["content"]})
            elif msg["role"] in ("user", "tool"):
                # Tool results become user messages with tool_result content blocks
                if msg["role"] == "tool":
                    # If the last message is a user role, append to it; otherwise create new
                    tool_result_block = {
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_use_id", "unknown"),
                        "content": msg["content"],
                    }
                    if api_messages and api_messages[-1]["role"] == "user":
                        content = api_messages[-1]["content"]
                        if isinstance(content, str):
                            api_messages[-1]["content"] = [{"type": "text", "text": content}, tool_result_block]
                        elif isinstance(content, list):
                            content.append(tool_result_block)
                    else:
                        api_messages.append({"role": "user", "content": [tool_result_block]})
                else:
                    api_messages.append({"role": "user", "content": msg["content"]})

        # Convert tools to Anthropic format
        anthropic_tools = []
        for tool in tools:
            anthropic_tools.append({
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool.get("input_schema", {"type": "object", "properties": {}}),
            })

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_msg,
            messages=api_messages if api_messages else [{"role": "user", "content": "Begin."}],
            tools=anthropic_tools if anthropic_tools else None,
        )

        # Parse response
        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(tool_name=block.name, arguments=block.input))

        return AgentResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    def supports_tools(self) -> bool:
        return True
```

### File: `src/agents/openai_agent.py`

```python
"""OpenAI agent for swap demo — proves the harness is agent-agnostic."""
import os
import json
from openai import AsyncOpenAI

from src.agents.base import BaseAgent
from src.harness.models import AgentResponse, ToolCall


class OpenAIAgent(BaseAgent):
    def __init__(self, model: str = "gpt-4o-mini"):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def run(self, messages: list[dict], tools: list[dict]) -> AgentResponse:
        # Convert to OpenAI format
        oai_messages = []
        for msg in messages:
            if msg["role"] in ("system", "user", "assistant"):
                oai_messages.append({"role": msg["role"], "content": msg["content"]})
            elif msg["role"] == "tool":
                oai_messages.append({
                    "role": "tool",
                    "content": msg["content"],
                    "tool_call_id": msg.get("tool_call_id", "unknown"),
                })

        oai_tools = []
        for tool in tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            })

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=oai_messages,
            tools=oai_tools if oai_tools else None,
        )

        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    tool_name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        return AgentResponse(
            text=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

    def supports_tools(self) -> bool:
        return True
```

### Tests: `tests/test_agents.py`

Tests should NOT call real APIs. Mock the SDK clients.

1. `ClaudeAgent` raises `ValueError` without `ANTHROPIC_API_KEY`
2. `OpenAIAgent` raises `ValueError` without `OPENAI_API_KEY`
3. Mock a Claude response with tool_use blocks → `AgentResponse` has `tool_calls`
4. Mock an OpenAI response with function calls → `AgentResponse` has `tool_calls`
5. Both agents return valid `AgentResponse` objects (text + usage present)

---

## U9. FastAPI Endpoints

### File: `src/api/routes.py`

```python
"""
FastAPI API surface.

Endpoints:
- POST /run         — submit alert, run harness, return result
- GET  /runs/{id}   — get run status + checkpoint history
- GET  /runs/{id}/alarms — get alarms for a run
- POST /runs/{id}/escalation — human decision on CRITICAL escalation
- POST /replay      — replay from a checkpoint
- GET  /health      — health check
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.harness.guardrails import GuardrailEngine
from src.harness.loop import HarnessLoop
from src.harness.material import MaterialHandler
from src.harness.models import Alert, CheckpointStage, EscalationDecision
from src.db.store import CheckpointStore
from src.tools import create_registry


_store: CheckpointStore | None = None
_guardrails: GuardrailEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _guardrails
    _store = CheckpointStore()
    await _store.connect()
    _guardrails = GuardrailEngine.from_yaml("guardrails.yaml")
    yield
    if _store:
        await _store.close()


app = FastAPI(
    title="Ops Runbook Harness",
    description="AI agent harness for infrastructure incident remediation",
    version="0.1.0",
    lifespan=lifespan,
)


def _get_agent():
    """Create the configured agent. Defaults to Claude, falls back to mock."""
    agent_type = os.environ.get("AGENT_TYPE", "claude")
    if agent_type == "openai":
        from src.agents.openai_agent import OpenAIAgent
        return OpenAIAgent()
    elif agent_type == "claude":
        from src.agents.claude_agent import ClaudeAgent
        return ClaudeAgent()
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


class RunRequest(BaseModel):
    service: str
    severity: str
    description: str
    source: str = "api"
    metadata: dict = {}


class ReplayRequest(BaseModel):
    run_id: str
    replay_from: str  # "CP1_ALERT_PARSED", "CP2_HYPOTHESIS_FORMED", etc.
    alert: dict


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ops-runbook-harness"}


@app.post("/run")
async def run_harness(request: RunRequest):
    try:
        alert = MaterialHandler.validate_alert(request.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    agent = _get_agent()
    registry = create_registry(_guardrails)
    loop = HarnessLoop(agent=agent, guardrails=_guardrails, store=_store, registry=registry)
    result = await loop.run(alert)
    return result


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = await _store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    checkpoints = await _store.get_checkpoints(run_id)
    return {**run, "checkpoints": checkpoints}


@app.get("/runs/{run_id}/alarms")
async def get_run_alarms(run_id: str):
    run = await _store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    # Alarms are stored in the run result
    result = run.get("result")
    if result and "alarms" in result:
        return {"run_id": run_id, "alarms": result["alarms"]}
    return {"run_id": run_id, "alarms": []}


@app.post("/runs/{run_id}/escalation")
async def handle_escalation(run_id: str, decision: EscalationDecision):
    run = await _store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run["status"] != "AWAITING_HUMAN":
        raise HTTPException(status_code=400, detail=f"Run is not awaiting human decision (status: {run['status']})")

    if decision.decision == "approve":
        await _store.update_run_status(run_id, "COMPLETED")
        return {"run_id": run_id, "status": "COMPLETED", "decision": "approved"}
    elif decision.decision == "reject":
        await _store.update_run_status(run_id, "FAILED")
        return {"run_id": run_id, "status": "FAILED", "decision": "rejected"}
    else:
        raise HTTPException(status_code=400, detail=f"Invalid decision: {decision.decision}. Must be 'approve' or 'reject'.")


@app.post("/replay")
async def replay_run(request: ReplayRequest):
    try:
        stage = CheckpointStage(request.replay_from)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid checkpoint stage: {request.replay_from}")

    try:
        alert = MaterialHandler.validate_alert(request.alert)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    agent = _get_agent()
    registry = create_registry(_guardrails)
    loop = HarnessLoop(agent=agent, guardrails=_guardrails, store=_store, registry=registry)
    result = await loop.run(alert, replay_from=stage, replay_run_id=request.run_id)
    return result
```

### Tests: `tests/test_api.py`

Use `httpx.AsyncClient` with FastAPI's `TestClient` or `ASGITransport`.
Mock the agent to avoid real API calls.

1. `GET /health` → 200 with `{"status": "ok"}`
2. `POST /run` with valid alert → 200 with run result (mock agent)
3. `POST /run` with missing `service` → 422
4. `GET /runs/{run_id}` for existing run → 200 with run data + checkpoints
5. `GET /runs/{run_id}` for non-existent run → 404
6. `POST /runs/{run_id}/escalation` with "approve" on AWAITING_HUMAN run → 200
7. `POST /runs/{run_id}/escalation` on non-AWAITING_HUMAN run → 400

---

## U10. Deployment + HARNESS.md

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .
RUN mkdir -p data

EXPOSE 8000

CMD ["python", "main.py"]
```

### HARNESS.md

Write this as the architecture deliverable. Structure:

1. **Overview** — one paragraph: what this harness does, what domain it operates in
2. **Architecture** — the four pillars, how they connect, a text diagram of the flow
3. **Guardrails** — what's declared in `guardrails.yaml`, how enforcement works, code pointer to `src/harness/guardrails.py`
4. **Checkpoints** — CP1-CP4 criteria, persistence to SQLite, replay mechanism, code pointer to `src/harness/checkpoints.py`
5. **Alarms** — alarm types with severity, structured output format, HITL escalation flow, code pointer to `src/harness/alarms.py`
6. **Material Handling** — input alert schema, output remediation report schema, code pointer to `src/harness/material.py`
7. **Agent Interface** — `BaseAgent` contract, how to swap agents, code pointer to `src/agents/base.py`
8. **Tools** — registry, allow-list enforcement, the 5 mock tools and their signatures
9. **API Endpoints** — table of all endpoints with method, path, description
10. **Running locally** — install, configure, run, test
11. **Deployment** — Railway setup, environment variables needed

---

## Fixture Data

### `fixtures/alerts/high_cpu_web_api.json`

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

### `fixtures/alerts/hung_query_postgres.json`

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

### `fixtures/alerts/dns_failure_cdn.json`

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

### `fixtures/alerts/unknown_service.json`

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

---

## Build Sequence for Sonnet

Execute these in order. Each unit should be fully tested before moving to the next.

| Step | Unit | What to build | Est. tokens |
|------|------|---------------|------------|
| 1 | U0 | Repo restructure, pyproject.toml, CLAUDE.md, guardrails.yaml, main.py, all `__init__.py` files | Low |
| 2 | U1 | `src/harness/models.py`, `src/agents/base.py`, `tests/test_models.py` | Low |
| 3 | U2 | `src/harness/guardrails.py`, `tests/test_guardrails.py` | Low |
| 4 | U3 | `src/harness/alarms.py`, `tests/test_alarms.py` | Low |
| 5 | U4 | `src/db/store.py`, `src/harness/checkpoints.py`, `tests/test_checkpoints.py` | Medium |
| 6 | U5 | `src/harness/material.py`, `tests/test_material.py` | Low |
| 7 | U6 | `src/tools/registry.py`, all 5 tool files, `src/tools/__init__.py`, `tests/test_tools.py` | Medium |
| 8 | U7 | `src/harness/loop.py`, `tests/test_loop.py` | High — use Opus |
| 9 | U8 | `src/agents/claude_agent.py`, `src/agents/openai_agent.py`, `tests/test_agents.py` | Medium |
| 10 | U9 | `src/api/routes.py`, `tests/test_api.py` | Medium |
| 11 | U10 | `Dockerfile`, `HARNESS.md`, `README.md` | Low |
| 12 | Fixtures | All 4 alert JSONs in `fixtures/alerts/` | Low |

**Recommendation**: Use Sonnet for all steps except U7 (the loop is the most architecturally critical piece and benefits from Opus reasoning). U8 agent implementations could also benefit from Opus for getting the SDK message format conversions right.
