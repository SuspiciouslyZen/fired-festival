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
| 1 | [x] | `docs/specs/units/u00-project-setup.md` | `pyproject.toml`, `CLAUDE.md`, `guardrails.yaml`, `main.py`, all `__init__.py` files, directory skeleton |
| 2 | [x] | `docs/specs/units/u01-models.md` | `src/harness/models.py`, `src/agents/base.py`, `tests/test_models.py` |
| 3 | [x] | `docs/specs/units/u02-guardrails.md` | `src/harness/guardrails.py`, `tests/test_guardrails.py` |
| 4 | [x] | `docs/specs/units/u03-alarms.md` | `src/harness/alarms.py`, `tests/test_alarms.py` |
| 5 | [x] | `docs/specs/units/u04-checkpoints.md` | `src/db/store.py`, `src/harness/checkpoints.py`, `tests/test_checkpoints.py` |
| 6 | [x] | `docs/specs/units/u05-material.md` | `src/harness/material.py`, `tests/test_material.py` |
| 7 | [x] | `docs/specs/units/u06-tools.md` | `src/tools/registry.py`, 5 mock tool files, `src/tools/__init__.py`, `tests/test_tools.py` |
| 8 | [x] | `docs/specs/units/u07-loop.md` | `src/harness/loop.py`, `tests/test_loop.py` |
| 9 | [x] | `docs/specs/units/u08-agents.md` | `src/agents/claude_agent.py`, `src/agents/openai_agent.py`, `tests/test_agents.py` |
| 10 | [x] | `docs/specs/units/u09-api.md` | `src/api/routes.py`, `tests/test_api.py` |
| 11 | [x] | `docs/specs/units/u10-deployment.md` | `Dockerfile`, `HARNESS.md`, `README.md` |
| 12 | [x] | `docs/specs/units/u11-fixtures.md` | 4 alert JSON files in `fixtures/alerts/` |

---

---

## Next steps (post-core, hackathon priority order)

### [x] U12 — Datadog instrumentation (~20 min Claude time)
**Files:** `src/harness/metrics.py`, edits to `src/harness/loop.py`

Dead code by default — activates only when `DD_API_KEY` env var is set. Uses `datadog` package with DogStatsD. No runtime cost if absent.

Metrics to emit at existing hook points in `loop.py`:
- `harness.run.completed` / `harness.run.failed` / `harness.run.awaiting_human` — counters on each `update_run_status` call
- `harness.alarm` — counter tagged `type:<AlarmType>` `severity:<Severity>` on every `alarm_manager.emit()`
- `harness.checkpoint.passed` / `harness.checkpoint.failed` — tagged `stage:<CheckpointStage>` after each CP evaluation
- `harness.tool.executed` — tagged `tool:<name>` `success:true|false` after each `registry.execute()`
- `harness.run.turns` — histogram of turn count at run completion
- `harness.run.tokens` — histogram of total token usage at run completion

Add to `pyproject.toml` dependencies: `datadog>=0.49.0`

**Datadog monitors to create once data flows:**
| Monitor | Condition |
|---------|-----------|
| Escalation spike | `harness.run.awaiting_human` > 3 in 5 min |
| Failure rate | `harness.run.failed` / total > 20% over 15 min |
| Critical alarm | `harness.alarm` with `severity:CRITICAL` any in 1 min |
| Plan blocked rate | `harness.checkpoint.failed` `stage:CP3_PLAN_VALIDATED` spiking |
| Token pressure | `harness.run.tokens` p95 > 40k |

---

### [x] U13 — Real-time web dashboard (~30 min Claude time)
**Files:** `src/api/dashboard.py` (or inline in `routes.py`), `src/static/index.html`

Single-page dashboard served by FastAPI at `GET /`. Polls existing API endpoints every 3 seconds — no new backend logic needed.

**Panels to show:**
- **Run feed** — live list of recent runs with status badge (COMPLETED green / FAILED red / AWAITING_HUMAN yellow), service name, timestamp, turn count
- **Alarm stream** — most recent alarms with type and severity, newest first
- **Checkpoint health** — pass rate per stage (CP1–CP4) across last N runs as a simple bar
- **HITL queue** — runs currently in AWAITING_HUMAN with approve/reject buttons wired to `POST /runs/{id}/escalation`
- **Stats bar** — total runs, success rate, avg tokens

**Implementation notes:**
- Serve `index.html` as a static file from FastAPI (`app.mount("/static", StaticFiles(...))` + redirect `/` → `/static/index.html`)
- Pure HTML/JS, no build step, no framework — vanilla fetch + setInterval polling
- Add `GET /runs` endpoint (list of recent runs, limit 50) to `routes.py` to support the run feed panel
- Style with a dark ops-style theme — this is a demo, make it look good

---

### [x] U14 — Alert trigger page (~20 min Claude time)
**Files:** `src/static/trigger.html`, add `GET /runs` list endpoint to `routes.py`

Second page at `/trigger`. Lets you fire any alert at the harness with one click — primary demo input interface for the hackathon.

**Layout:** Grid of alert cards, one per fixture. Each card shows:
- Service name + severity badge
- Description (truncated)
- **Trigger** button — POSTs to `POST /run`, shows spinner while running
- Inline result: status badge + run_id link to the dashboard once complete

**Fixture cards to include:**
| Card | Payload |
|------|---------|
| web-api CPU spike | `fixtures/alerts/high_cpu_web_api.json` |
| postgres hung query | `fixtures/alerts/hung_query_postgres.json` |
| CDN DNS failure | `fixtures/alerts/dns_failure_cdn.json` |
| Unknown service | `fixtures/alerts/unknown_service.json` |
| Custom alert | Free-form fields: service dropdown, severity, description — lets you craft arbitrary inputs live |

**Implementation notes:**
- Hardcode fixture payloads as JS constants — no file reads needed
- Disable the button and show spinner on click, re-enable on response
- Link the dashboard (`/`) in the nav so the two pages connect
- Same dark ops theme as the dashboard

---

### U15 — AWS EC2 webhook input (future, if time allows)
**Files:** `src/api/routes.py` (add `POST /webhook/ec2`), `src/harness/material.py` (add EC2 alert normalizer)

When an EC2 instance stops unexpectedly, CloudWatch → EventBridge → HTTP POST to `/webhook/ec2`. The endpoint normalizes the EC2 event format into an `Alert` and calls the harness loop — same path as `/run`.

**EC2 event → Alert mapping:**
- `service` ← EC2 instance tags (`Name` tag or instance ID)
- `severity` ← `"critical"`
- `description` ← `"EC2 instance {id} entered stopped state unexpectedly"`
- `source` ← `"aws-eventbridge"`
- `metadata` ← full EC2 event payload

**To wire up:**
1. Add `POST /webhook/ec2` endpoint that accepts the EventBridge `EC2 Instance State-change Notification` JSON
2. Create an EventBridge rule: source `aws.ec2`, detail-type `EC2 Instance State-change Notification`, state `stopped` → HTTP target pointing at the deployed harness URL
3. Add `restart_service` tool behavior that actually calls EC2 `start_instances` via boto3 (swap mock executor)

**Note:** The mock `restart_service` tool already returns `new_status: healthy` — the loop will complete correctly in simulation before the real boto3 call is wired up.

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
