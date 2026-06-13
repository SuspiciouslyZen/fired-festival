# U5. Material Handling

## Dependencies

- [[u01-models]] — `src/harness/models.py` (`Alert`, `RemediationReport`, `Alarm`, `CheckpointResult`)

**Files created by this unit:**
- `src/harness/material.py`
- `tests/test_material.py`

---

## File: `src/harness/material.py`

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

---

## Tests: `tests/test_material.py`

1. Valid alert dict validates successfully
2. Missing `service` → `ValueError`
3. Missing `severity` → `ValueError`
4. Missing `description` → `ValueError`
5. Extra fields in metadata preserved
6. `build_report` returns complete report with all fields
7. Report serializes to JSON round-trip without data loss
