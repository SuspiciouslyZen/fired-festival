# U0. Project Setup

## Dependencies

None — this is the first unit. Creates the skeleton everything else builds on.

**Files created by this unit:**
- `pyproject.toml`
- `CLAUDE.md`
- `guardrails.yaml`
- `main.py`
- `src/__init__.py`
- `src/harness/__init__.py`
- `src/agents/__init__.py`
- `src/tools/__init__.py`
- `src/db/__init__.py`
- `src/api/__init__.py`
- `tests/__init__.py`
- `data/` directory
- All directories under `src/`, `tests/`, `fixtures/`

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

## pyproject.toml

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

---

## guardrails.yaml

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

---

## main.py

```python
import uvicorn
from src.api.routes import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Repo restructure commands

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
