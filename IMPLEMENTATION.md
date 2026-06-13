# Implementation Plan

Build the Ops Runbook Harness in unit order. Each unit has a spec file at `docs/specs/units/`. Read the relevant unit file before starting that unit — do not read ahead.

## How to work

1. Read the unit spec file for the current step
2. Write all files listed in the spec exactly as specified — no additions, no omissions
3. Run `pytest tests/test_<unit>.py -v` and confirm all tests pass before moving on
4. Mark the unit done below and proceed to the next

After all units: run `pytest tests/ -v` to confirm the full suite passes.

---

## Build order

| # | Status | Unit file | Key outputs |
|---|--------|-----------|-------------|
| 1 | [ ] | `docs/specs/units/u00-project-setup.md` | `pyproject.toml`, `CLAUDE.md`, `guardrails.yaml`, `main.py`, all `__init__.py` files, directory skeleton |
| 2 | [ ] | `docs/specs/units/u01-models.md` | `src/harness/models.py`, `src/agents/base.py`, `tests/test_models.py` |
| 3 | [ ] | `docs/specs/units/u02-guardrails.md` | `src/harness/guardrails.py`, `tests/test_guardrails.py` |
| 4 | [ ] | `docs/specs/units/u03-alarms.md` | `src/harness/alarms.py`, `tests/test_alarms.py` |
| 5 | [ ] | `docs/specs/units/u04-checkpoints.md` | `src/db/store.py`, `src/harness/checkpoints.py`, `tests/test_checkpoints.py` |
| 6 | [ ] | `docs/specs/units/u05-material.md` | `src/harness/material.py`, `tests/test_material.py` |
| 7 | [ ] | `docs/specs/units/u06-tools.md` | `src/tools/registry.py`, 5 mock tool files, `src/tools/__init__.py`, `tests/test_tools.py` |
| 8 | [ ] | `docs/specs/units/u07-loop.md` | `src/harness/loop.py`, `tests/test_loop.py` |
| 9 | [ ] | `docs/specs/units/u08-agents.md` | `src/agents/claude_agent.py`, `src/agents/openai_agent.py`, `tests/test_agents.py` |
| 10 | [ ] | `docs/specs/units/u09-api.md` | `src/api/routes.py`, `tests/test_api.py` |
| 11 | [ ] | `docs/specs/units/u10-deployment.md` | `Dockerfile`, `HARNESS.md`, `README.md` |
| 12 | [ ] | `docs/specs/units/u11-fixtures.md` | 4 alert JSON files in `fixtures/alerts/` |

---

## Rules

- **Do not skip units.** Each unit's outputs are imported by later units.
- **Do not modify** `docs/specs/IMPLEMENTATION-SPEC.md` or any file in `docs/specs/units/`.
- **Tests must pass** before moving to the next unit. If a test fails, fix the implementation — do not alter the test to make it pass.
- **No extra features.** Write exactly what the spec says. No added abstractions, no extra error handling, no additional files.
- **Import paths** use `src.` prefix (e.g., `from src.harness.models import Alert`).
- **U7 (loop) is the most complex unit.** If on Sonnet, consider switching to Opus for that step.
- **U8 (agents) mocks SDK calls in tests.** No real API calls in tests.

---

## Install & test commands

```bash
pip install -e ".[dev]"      # install with dev deps
pytest tests/ -v             # full suite
pytest tests/test_X.py -v    # single unit
pyright src/                 # type check
python main.py               # start server (port 8000)
```
