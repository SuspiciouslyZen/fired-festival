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
