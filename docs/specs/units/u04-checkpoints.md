# U4. Checkpoint Module + SQLite Store

## Dependencies

- [[u01-models]] — `src/harness/models.py` (`CheckpointResult`, `CheckpointStage`, `GuardrailDecision`)
- [[u02-guardrails]] — `src/harness/guardrails.py` (`GuardrailEngine`)

**Files created by this unit:**
- `src/db/store.py`
- `src/harness/checkpoints.py`
- `tests/test_checkpoints.py`

---

## File: `src/db/store.py`

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

---

## File: `src/harness/checkpoints.py`

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

---

## Tests: `tests/test_checkpoints.py`

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
