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

### U15 — AWS EC2 webhook input (~15 min Claude time)
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

### U16 — AWS service discovery (~10 min Claude time)
**Files:** `src/aws/discovery.py`, `src/harness/guardrails.py` (wire in discovered services to CP1)

Use the AWS Resource Groups Tagging API to enumerate all resources tagged `Monitoring:true` at startup. The discovered service names replace (or augment) the static allowed-services list that CP1 validates against.

**Implementation:**
- Add `boto3>=1.34` to `pyproject.toml`
- `src/aws/discovery.py` — `list_monitored_services() -> list[str]`: calls `resourcegroupstaggingapi.get_resources(TagFilters=[{"Key": "Monitoring", "Values": ["true"]}])`, extracts the `Name` tag or falls back to the resource ARN's trailing segment
- Call `list_monitored_services()` at startup in `main.py` and inject into `GuardrailEngine` config so CP1 accepts discovered service names
- Falls back to the static list if boto3 call fails (no credentials, wrong region, etc.) — log a warning, do not crash

**AWS side (no CDK needed):** Ensure the EC2 instance profile has `tag:GetResources` permission on `*`.

---

### U17 — Real `check_status` tool via CloudWatch (~15 min Claude time)
**Files:** `src/tools/check_status.py` (replace mock executor), `src/aws/cloudwatch.py`

Replace the hardcoded `SERVICE_STATUS` dict with live CloudWatch `GetMetricStatistics` calls for the monitored service.

**Metrics to fetch per service (5-min window, Average statistic):**
| CloudWatch metric | Namespace | Dimension |
|---|---|---|
| `CPUUtilization` | `AWS/EC2` | `InstanceId` |
| `mem_used_percent` | `CWAgent` | `InstanceId` (requires CW agent) |
| `StatusCheckFailed` | `AWS/EC2` | `InstanceId` |

**Implementation:**
- `src/aws/cloudwatch.py` — `get_instance_metrics(instance_id: str) -> dict`: fetches the three metrics above and returns `{status, cpu_percent, memory_percent, status_check_failed}`
- `check_status` executor: look up instance ID from service name via the discovery map built in U16, call `get_instance_metrics`, return normalized dict matching the existing schema so the loop and CP4 don't need changes
- If CloudWatch returns no data points (instance too new, CW agent not installed), return `{"status": "unknown"}` — do not raise

---

### U18 — Real `restart_service` tool via EC2/ECS (~10 min Claude time)
**Files:** `src/tools/restart_service.py` (replace mock executor), `src/aws/ec2.py`

Replace the mock executor with real EC2 `stop_instances` + `start_instances` calls (or ECS `update_service` with `forceNewDeployment` for ECS tasks).

**Implementation:**
- `src/aws/ec2.py` — `restart_ec2_instance(instance_id: str) -> dict`: calls `stop_instances`, waits for `stopped` state (waiter, 60s timeout), then `start_instances`. Returns `{success, new_status, instance_id}`.
- `restart_service` executor: resolve service → instance ID via discovery map, call `restart_ec2_instance`, surface result
- Guardrail note: `restart_service` must remain on the allowed list in `guardrails.yaml` — it is already there.

**IAM permissions required on instance profile:** `ec2:StopInstances`, `ec2:StartInstances`, `ec2:DescribeInstanceStatus` scoped to instances tagged `Monitoring:true`.

---

### U19 — Real `read_logs` tool via CloudWatch Logs (~10 min Claude time)
**Files:** `src/tools/read_logs.py` (replace mock executor), `src/aws/cloudwatch.py` (extend)

Replace mock log lines with real CloudWatch Logs `filter_log_events` calls.

**Implementation:**
- Add `get_recent_logs(log_group: str, minutes: int = 15) -> list[str]` to `src/aws/cloudwatch.py`
- `read_logs` executor: resolve service → log group name (convention: `/aws/ec2/<service-name>` or from a tag), call `get_recent_logs(minutes=15)`, return last 50 lines
- If log group does not exist or has no events, return `{"lines": [], "note": "no logs found"}` — do not raise

**IAM permissions required:** `logs:FilterLogEvents`, `logs:DescribeLogGroups` on the relevant log groups.

---

### U20 — CDK stack for AWS infrastructure (~15 min Claude time)
**Files:** `infra/app.py`, `infra/harness_stack.py`, `infra/requirements.txt`

CDK app that provisions the AWS-side resources needed for U15–U19. Deployed once; the harness app itself runs on the existing EC2 instance.

**Resources to create:**

| Resource | Purpose |
|---|---|
| `aws_sns.Topic` (`HarnessAlerts`) | Receives CloudWatch Alarm notifications |
| `aws_sns_subscriptions.UrlSubscription` | POSTs SNS notifications to `POST /webhook/ec2` on the harness EC2 public IP |
| `aws_cloudwatch.Alarm` (per tagged instance, created at synth time via discovery) | Triggers on `StatusCheckFailed >= 1` for 2 consecutive periods |
| `aws_iam.Role` + `ManagedPolicy` | Instance profile for the harness EC2: tag read, CW metrics read, CW logs read, EC2 stop/start scoped to `Monitoring:true` tagged instances |
| `aws_events.Rule` (EC2 state-change) | EventBridge rule: EC2 state → `stopped` → SNS topic (backup path alongside CW alarms) |

**Implementation notes:**
- CDK app reads tagged instance IDs at synth time via boto3 (same `list_monitored_services` logic) to create per-instance CloudWatch Alarms
- `infra/requirements.txt`: `aws-cdk-lib>=2.140`, `constructs>=10`, `boto3>=1.34`
- Deploy: `cd infra && cdk deploy`
- No unit tests for the CDK stack — validate with `cdk synth` producing valid CloudFormation

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
