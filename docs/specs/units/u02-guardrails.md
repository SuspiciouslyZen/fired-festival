# U2. Guardrails Module

## Dependencies

- [[u00-project-setup]] — `guardrails.yaml` at repo root
- [[u01-models]] — `src/harness/models.py` (`GuardrailDecision` enum)

**Files created by this unit:**
- `src/harness/guardrails.py`
- `tests/test_guardrails.py`

---

## File: `src/harness/guardrails.py`

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

---

## Tests: `tests/test_guardrails.py`

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
