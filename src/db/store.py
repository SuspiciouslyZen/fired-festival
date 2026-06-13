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
            (checkpoint_id, run_id, stage, int(passed), json.dumps(state, default=str), failure_reason, datetime.now(timezone.utc).isoformat()),
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

    async def list_runs(self, limit: int = 50) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT run_id, alert_id, status, started_at, completed_at, result_json FROM runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "run_id": r[0], "alert_id": r[1], "status": r[2],
                "started_at": r[3], "completed_at": r[4],
                "result": json.loads(r[5]) if r[5] else None,
            }
            for r in rows
        ]

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
