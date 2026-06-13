import pytest

from src.db.store import CheckpointStore
from src.harness.checkpoints import CheckpointManager
from src.harness.guardrails import GuardrailConfig, GuardrailEngine
from src.harness.models import CheckpointStage


@pytest.fixture
async def store():
    s = CheckpointStore(db_path=":memory:")
    await s.connect()
    yield s
    await s.close()


@pytest.fixture
def engine():
    config = GuardrailConfig(
        allowed_actions=["check_status", "restart_service", "read_logs", "kill_query", "flush_dns"],
        requires_approval=["restart_service"],
    )
    return GuardrailEngine(config)


@pytest.fixture
async def manager(store, engine):
    return CheckpointManager(store=store, guardrail_engine=engine)


# 1. CP1 pass
async def test_cp1_pass(manager):
    result = await manager.evaluate_cp1("run-1", {"service": "web-api", "severity": "high"})
    assert result.passed is True
    assert result.state["service"] == "web-api"


# 2. CP1 fail: unknown service
async def test_cp1_fail_unknown_service(manager):
    result = await manager.evaluate_cp1("run-1", {"service": "unknown-svc", "severity": "high"})
    assert result.passed is False
    assert "unknown-svc" in result.failure_reason


# 3. CP2 pass
async def test_cp2_pass(manager):
    result = await manager.evaluate_cp2("run-1", {"confidence": 0.8, "hypothesis": "memory leak"})
    assert result.passed is True


# 4. CP2 fail: low confidence
async def test_cp2_fail_low_confidence(manager):
    result = await manager.evaluate_cp2("run-1", {"confidence": 0.3, "hypothesis": "memory leak"})
    assert result.passed is False
    assert "0.6" in result.failure_reason


# 5. CP3 pass: all actions allowed
async def test_cp3_pass(manager):
    result = await manager.evaluate_cp3("run-1", ["check_status", "read_logs"])
    assert result.passed is True


# 6. CP3 fail: blocked action
async def test_cp3_fail_blocked(manager):
    result = await manager.evaluate_cp3("run-1", ["check_status", "drop_table"])
    assert result.passed is False
    assert "drop_table" in result.failure_reason


# 7. CP4 pass: healthy
async def test_cp4_pass(manager):
    result = await manager.evaluate_cp4("run-1", {"status": "healthy"})
    assert result.passed is True


# 8. CP4 fail: degraded
async def test_cp4_fail(manager):
    result = await manager.evaluate_cp4("run-1", {"status": "degraded"})
    assert result.passed is False


# 9. Checkpoints persisted to SQLite
async def test_checkpoints_persisted(manager, store):
    await manager.evaluate_cp1("run-99", {"service": "redis", "severity": "low"})
    await manager.evaluate_cp2("run-99", {"confidence": 0.9, "hypothesis": "OOM"})
    rows = await store.get_checkpoints("run-99")
    assert len(rows) == 2
    assert rows[0]["stage"] == "CP1_ALERT_PARSED"
    assert rows[1]["stage"] == "CP2_HYPOTHESIS_FORMED"


# 10. Multiple runs are isolated
async def test_run_isolation(manager, store):
    await manager.evaluate_cp1("run-A", {"service": "redis", "severity": "low"})
    await manager.evaluate_cp1("run-B", {"service": "postgres", "severity": "high"})
    rows_a = await store.get_checkpoints("run-A")
    rows_b = await store.get_checkpoints("run-B")
    assert len(rows_a) == 1
    assert len(rows_b) == 1
    assert rows_a[0]["run_id"] == "run-A"
    assert rows_b[0]["run_id"] == "run-B"


# 11. Replay: save CP1 state, load it back
async def test_replay_state(manager, store):
    alert = {"service": "cdn", "severity": "critical"}
    result = await manager.evaluate_cp1("run-replay", alert)
    loaded = await manager.load_replay_state("run-replay", CheckpointStage.CP1_ALERT_PARSED)
    assert loaded is not None
    assert loaded["service"] == "cdn"


# 12. Database auto-creates on connect
async def test_db_auto_creates(tmp_path):
    db_file = str(tmp_path / "subdir" / "test.db")
    s = CheckpointStore(db_path=db_file)
    await s.connect()
    await s.create_run("run-x", "alert-x")
    row = await s.get_run("run-x")
    assert row is not None
    await s.close()
