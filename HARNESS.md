# Ops Runbook Harness

## 1. Overview

The Ops Runbook Harness is an AI agent harness that drives a language model through a structured incident remediation workflow. Given an infrastructure alert (service name, severity, description), the harness orchestrates the agent through four mandatory stages — alert validation, diagnosis, plan validation, and health verification — before producing a structured remediation report. It operates in the infrastructure operations domain, targeting staging and production service incidents involving services such as web APIs, databases, caches, CDNs, and worker queues.

---

## 2. Architecture

The harness is built on four pillars that the core loop (`src/harness/loop.py`) coordinates:

```
Alert (JSON)
     │
     ▼
┌─────────────┐    ┌──────────────┐
│  Material   │───▶│  Guardrails  │
│  Handler    │    │  Engine      │
│ (validate)  │    │ (allow-list) │
└─────────────┘    └──────┬───────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  Harness    │◀────── BaseAgent (Claude / OpenAI)
                   │  Loop       │──────▶ ToolRegistry
                   │             │──────▶ AlarmManager
                   │             │──────▶ CheckpointManager
                   └──────┬──────┘
                          │
              ┌───────────┴────────────┐
              ▼                        ▼
     RemediationReport           Escalation
     (COMPLETED)                 (AWAITING_HUMAN)
```

**Flow:**
1. `POST /run` → MaterialHandler validates the alert
2. Loop starts: CP1 checks service/severity are known
3. Agent loop begins: agent calls tools (check_status, read_logs, etc.)
4. Agent emits `{"diagnosis": ...}` → CP2 checks confidence threshold
5. Agent emits `{"plan": ...}` → CP3 checks all planned actions are on allow-list
6. Agent executes tools and emits `{"resolution": ...}` → CP4 checks health status
7. Loop returns `RemediationReport` (COMPLETED) or escalates (AWAITING_HUMAN)

---

## 3. Guardrails

Declared in `guardrails.yaml` at the repo root:

- **`allowed_actions`** — explicit allow-list of tool names the agent may invoke
- **`requires_approval`** — subset of allowed actions that need human approval before execution
- **`production_requires_approval`** — if true, all actions in production require approval
- **`max_turns`** / **`token_budget`** — loop termination limits
- **`severity_overrides`** — override default alarm severity by alarm type

Enforcement: before every tool call, `GuardrailEngine.check_action()` returns `ALLOWED`, `BLOCKED`, or `NEEDS_APPROVAL`. `BLOCKED` triggers a `DESTRUCTIVE_ACTION_REQUESTED` alarm and halts with `AWAITING_HUMAN`. `NEEDS_APPROVAL` returns a `needs_approval: true` result to the agent without executing.

Code: `src/harness/guardrails.py`

---

## 4. Checkpoints

Four mandatory gates in the workflow:

| Stage | Criteria | Failure behavior |
|-------|----------|-----------------|
| **CP1** `CP1_ALERT_PARSED` | Service is in known-services list; severity is valid | Emit `UNKNOWN_SERVICE` alarm → FAILED |
| **CP2** `CP2_HYPOTHESIS_FORMED` | Agent confidence ≥ 0.6 and hypothesis is non-empty | Emit `CONFIDENCE_LOW` alarm → prompt agent for more evidence |
| **CP3** `CP3_PLAN_VALIDATED` | All planned actions are on the guardrail allow-list | Emit `DESTRUCTIVE_ACTION_REQUESTED` alarm → AWAITING_HUMAN |
| **CP4** `CP4_HEALTH_CHECK` | Post-action service status is `healthy`, `recovered`, or `ok` | Emit `REMEDIATION_FAILED` alarm → AWAITING_HUMAN |

Each checkpoint result is persisted to SQLite (`data/harness.db`) via `CheckpointStore`. Replay: pass `replay_from` + `replay_run_id` to `HarnessLoop.run()` to skip already-passed checkpoints by loading their saved state.

Code: `src/harness/checkpoints.py`, `src/db/store.py`

---

## 5. Alarms

| Alarm type | Default severity | Meaning |
|------------|-----------------|---------|
| `UNKNOWN_SERVICE` | WARNING | CP1 failed — service not recognized |
| `DESTRUCTIVE_ACTION_REQUESTED` | CRITICAL | Agent tried a blocked action or plan contained blocked action |
| `REMEDIATION_FAILED` | CRITICAL | CP4 failed — service still unhealthy after fix |
| `TURN_LIMIT_REACHED` | WARNING | Agent exhausted turn or token budget |
| `CONFIDENCE_LOW` | INFO | Agent diagnosis confidence below threshold |

CRITICAL alarms halt the loop and set status to `AWAITING_HUMAN`. WARNING/INFO alarms are recorded but do not halt. Severity can be overridden per alarm type in `guardrails.yaml` under `severity_overrides`.

HITL flow: `POST /runs/{run_id}/escalation` with `{"decision": "approve" | "reject"}` resolves a run in `AWAITING_HUMAN` state.

Code: `src/harness/alarms.py`

---

## 6. Material Handling

**Input alert schema** (`Alert` model):
- `service` (required) — service name
- `severity` (required) — alert severity string
- `description` (required) — human-readable description
- `source` (default: `"manual"`) — origin of alert
- `metadata` (default: `{}`) — arbitrary extra fields

**Output remediation report schema** (`RemediationReport` model):
- `run_id`, `alert` — run identity
- `diagnosis` — agent's hypothesis string
- `actions_taken` — list of tool calls with arguments and results
- `outcomes` — list of outcome strings
- `metrics_before` / `metrics_after` — service metrics from check_status calls
- `downstream_effects` — list of downstream impact strings
- `resolution_status` — `"resolved"` or other
- `alarms` — all alarms emitted during the run
- `checkpoints` — all checkpoint results

`MaterialHandler.validate_alert()` raises `ValueError` with field-level messages on invalid input.

Code: `src/harness/material.py`

---

## 7. Agent Interface

All agents implement `BaseAgent` (abstract):

```python
class BaseAgent(ABC):
    async def run(self, messages: list[dict], tools: list[dict]) -> AgentResponse: ...
    def supports_tools(self) -> bool: ...
```

`AgentResponse` contains `text`, `tool_calls`, `finish_reason`, and `usage`. The loop never imports agent-specific code — it only calls `BaseAgent.run()`.

**Swapping agents:** set the `AGENT_TYPE` environment variable to `"claude"` (default) or `"openai"`. The API creates the agent per-request in `_get_agent()`.

Two implementations ship:
- `ClaudeAgent` — Anthropic SDK, requires `ANTHROPIC_API_KEY`
- `OpenAIAgent` — OpenAI SDK, requires `OPENAI_API_KEY`

Code: `src/agents/base.py`, `src/agents/claude_agent.py`, `src/agents/openai_agent.py`

---

## 8. Tools

Tools are registered with `ToolRegistry` and never called directly by the agent. The loop calls `registry.execute(tool_name, arguments)` which checks guardrails first.

| Tool | Description | Key parameters |
|------|-------------|---------------|
| `check_status` | Health metrics for a service | `service: str` |
| `restart_service` | Restart a service (mutating) | `service: str` |
| `read_logs` | Recent log lines for a service | `service: str`, `lines: int` |
| `kill_query` | Kill a long-running DB query (mutating) | `query_id: str` |
| `flush_dns` | Flush DNS cache for a service | `service: str` |

`create_registry(guardrails)` in `src/tools/__init__.py` registers all five tools and returns a configured `ToolRegistry`.

---

## 9. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `POST` | `/run` | Submit alert, run harness, return result |
| `GET` | `/runs/{run_id}` | Get run status and checkpoint history |
| `GET` | `/runs/{run_id}/alarms` | Get alarms for a run |
| `POST` | `/runs/{run_id}/escalation` | Submit human decision (`approve`/`reject`) for escalated run |
| `POST` | `/replay` | Replay a prior run from a specific checkpoint stage |

---

## 10. Running Locally

```bash
# Install
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure
export ANTHROPIC_API_KEY=your-key   # or OPENAI_API_KEY
export AGENT_TYPE=claude             # or openai

# Run server
python main.py   # http://localhost:8000

# Run tests
pytest tests/ -v

# Type check
pyright src/
```

---

## 11. Deployment

The harness deploys as a single Docker container.

```bash
docker build -t ops-runbook-harness .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=your-key \
  -e AGENT_TYPE=claude \
  ops-runbook-harness
```

**Railway deployment:**
1. Connect your GitHub repo to Railway
2. Railway auto-detects the `Dockerfile`
3. Set environment variables in the Railway dashboard:
   - `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
   - `AGENT_TYPE` (`claude` or `openai`)
4. The `data/` directory with `harness.db` is ephemeral — mount a Railway volume at `/app/data` for persistence across deploys
