"""
FastAPI API surface.

Endpoints:
- POST /run         — submit alert, run harness, return result
- GET  /runs/{id}   — get run status + checkpoint history
- GET  /runs/{id}/alarms — get alarms for a run
- POST /runs/{id}/escalation — human decision on CRITICAL escalation
- POST /replay      — replay from a checkpoint
- GET  /health      — health check
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.harness.guardrails import GuardrailEngine
from src.harness.loop import HarnessLoop
from src.harness.material import MaterialHandler
from src.harness.models import Alert, CheckpointStage, EscalationDecision
from src.db.store import CheckpointStore
from src.tools import create_registry


_store: CheckpointStore | None = None
_guardrails: GuardrailEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _guardrails
    _store = CheckpointStore()
    await _store.connect()
    _guardrails = GuardrailEngine.from_yaml("guardrails.yaml")
    yield
    if _store:
        await _store.close()


app = FastAPI(
    title="Ops Runbook Harness",
    description="AI agent harness for infrastructure incident remediation",
    version="0.1.0",
    lifespan=lifespan,
)

_static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "src", "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


def _get_agent():
    """Create the configured agent. Defaults to Claude, falls back to mock."""
    agent_type = os.environ.get("AGENT_TYPE", "claude")
    if agent_type == "openai":
        from src.agents.openai_agent import OpenAIAgent
        return OpenAIAgent()
    elif agent_type == "mock":
        from src.agents.mock_agent import MockAgent
        return MockAgent()
    elif agent_type == "claude":
        from src.agents.claude_agent import ClaudeAgent
        return ClaudeAgent()
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


class RunRequest(BaseModel):
    service: str
    severity: str
    description: str
    source: str = "api"
    metadata: dict = {}


class ReplayRequest(BaseModel):
    run_id: str
    replay_from: str  # "CP1_ALERT_PARSED", "CP2_HYPOTHESIS_FORMED", etc.
    alert: dict


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ops-runbook-harness"}


@app.get("/runs")
async def list_runs(limit: int = 50):
    return await _store.list_runs(limit=min(limit, 100))


@app.post("/run")
async def run_harness(request: RunRequest):
    try:
        alert = MaterialHandler.validate_alert(request.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        agent = _get_agent()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    registry = create_registry(_guardrails)
    loop = HarnessLoop(agent=agent, guardrails=_guardrails, store=_store, registry=registry)
    result = await loop.run(alert)
    return result


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = await _store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    checkpoints = await _store.get_checkpoints(run_id)
    return {**run, "checkpoints": checkpoints}


@app.get("/runs/{run_id}/alarms")
async def get_run_alarms(run_id: str):
    run = await _store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    # Alarms are stored in the run result
    result = run.get("result")
    if result and "alarms" in result:
        return {"run_id": run_id, "alarms": result["alarms"]}
    return {"run_id": run_id, "alarms": []}


@app.post("/runs/{run_id}/escalation")
async def handle_escalation(run_id: str, decision: EscalationDecision):
    run = await _store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run["status"] != "AWAITING_HUMAN":
        raise HTTPException(status_code=400, detail=f"Run is not awaiting human decision (status: {run['status']})")

    if decision.decision == "approve":
        await _store.update_run_status(run_id, "COMPLETED")
        return {"run_id": run_id, "status": "COMPLETED", "decision": "approved"}
    elif decision.decision == "reject":
        await _store.update_run_status(run_id, "FAILED")
        return {"run_id": run_id, "status": "FAILED", "decision": "rejected"}
    else:
        raise HTTPException(status_code=400, detail=f"Invalid decision: {decision.decision}. Must be 'approve' or 'reject'.")


@app.post("/replay")
async def replay_run(request: ReplayRequest):
    try:
        stage = CheckpointStage(request.replay_from)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid checkpoint stage: {request.replay_from}")

    try:
        alert = MaterialHandler.validate_alert(request.alert)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    agent = _get_agent()
    registry = create_registry(_guardrails)
    loop = HarnessLoop(agent=agent, guardrails=_guardrails, store=_store, registry=registry)
    result = await loop.run(alert, replay_from=stage, replay_run_id=request.run_id)
    return result
