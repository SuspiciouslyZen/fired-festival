import pytest
import yaml

from src.harness.guardrails import GuardrailConfig, GuardrailEngine
from src.harness.models import GuardrailDecision


@pytest.fixture
def engine():
    config = GuardrailConfig(
        allowed_actions=["check_status", "restart_service", "read_logs", "kill_query", "flush_dns"],
        environment_scope="staging",
        production_requires_approval=True,
        max_turns=15,
        token_budget=50000,
        requires_approval=["restart_service", "kill_query"],
    )
    return GuardrailEngine(config)


@pytest.fixture
def tmp_yaml(tmp_path):
    def _write(data):
        p = tmp_path / "guardrails.yaml"
        p.write_text(yaml.dump(data))
        return p
    return _write


# 1. check_status in staging → ALLOWED
def test_check_status_staging_allowed(engine):
    assert engine.check_action("check_status") == GuardrailDecision.ALLOWED


# 2. delete_database → BLOCKED (not on allow-list)
def test_unknown_action_blocked(engine):
    assert engine.check_action("delete_database") == GuardrailDecision.BLOCKED


# 3. restart_service in staging → NEEDS_APPROVAL (on requires_approval list)
def test_restart_service_needs_approval(engine):
    assert engine.check_action("restart_service") == GuardrailDecision.NEEDS_APPROVAL


# 4. check_status in production → NEEDS_APPROVAL
def test_check_status_production_needs_approval(engine):
    assert engine.check_action("check_status", environment="production") == GuardrailDecision.NEEDS_APPROVAL


# 5. within limits → (True, None)
def test_check_limits_within(engine):
    ok, reason = engine.check_limits(14, 100)
    assert ok is True
    assert reason is None


# 6. turn limit hit → (False, reason)
def test_check_limits_turn_exceeded(engine):
    ok, reason = engine.check_limits(15, 100)
    assert ok is False
    assert reason is not None
    assert "Turn limit exceeded" in reason


# 7. token budget hit → (False, reason)
def test_check_limits_token_exceeded(engine):
    ok, reason = engine.check_limits(1, 50000)
    assert ok is False
    assert reason is not None
    assert "Token budget exceeded" in reason


# 8. from_yaml with valid file loads correctly
def test_from_yaml_valid(tmp_yaml):
    data = {
        "allowed_actions": ["check_status"],
        "environment_scope": "staging",
        "production_requires_approval": True,
        "max_turns": 10,
        "token_budget": 20000,
        "timeout_seconds": 60,
        "requires_approval": [],
        "severity_overrides": {},
    }
    path = tmp_yaml(data)
    eng = GuardrailEngine.from_yaml(path)
    assert eng.config.max_turns == 10
    assert eng.config.allowed_actions == ["check_status"]


# 9. from_yaml with malformed YAML raises ValueError
def test_from_yaml_malformed(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a list\n")
    with pytest.raises(ValueError):
        GuardrailEngine.from_yaml(bad)


# 10. empty allowed_actions blocks all actions
def test_empty_allowed_actions_blocks_all():
    config = GuardrailConfig(allowed_actions=[])
    eng = GuardrailEngine(config)
    assert eng.check_action("check_status") == GuardrailDecision.BLOCKED
    assert eng.check_action("restart_service") == GuardrailDecision.BLOCKED
