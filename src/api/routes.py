"""
FastAPI API surface.

Endpoints:
- POST /run         — submit alert, run harness, return result
- GET  /agents      — list agents with live reachability status
- GET  /runs        — list recent runs
- GET  /runs/{id}   — get run status + checkpoint history
- GET  /runs/{id}/alarms — get alarms for a run
- POST /runs/{id}/escalation — human decision on CRITICAL escalation
- POST /replay      — replay from a checkpoint
- GET  /health      — health check
"""
import asyncio
import logging
import os
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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

    try:
        from src.aws.discovery import list_monitored_services
        discovered = await asyncio.to_thread(list_monitored_services)
        if discovered:
            _guardrails.add_allowed_services(discovered)
            logger.info(f"AWS discovery: registered {len(discovered)} services: {discovered}")
    except Exception as e:
        logger.warning(f"AWS service discovery skipped: {e}")

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


def _get_agent(agent_type: str, model: str | None = None):
    if agent_type == "ollama":
        from src.agents.ollama_agent import OllamaAgent
        return OllamaAgent(model=model or None)
    elif agent_type == "claude":
        from src.agents.claude_agent import ClaudeAgent
        return ClaudeAgent()
    elif agent_type == "openai":
        from src.agents.openai_agent import OpenAIAgent
        return OpenAIAgent()
    elif agent_type == "openrouter":
        from src.agents.openrouter_agent import OpenRouterAgent
        return OpenRouterAgent(model=model or None)
    elif agent_type == "mock":
        from src.agents.mock_agent import MockAgent
        return MockAgent()
    else:
        raise ValueError(f"Unknown agent_type '{agent_type}'. Valid: ollama, claude, openai, openrouter, mock")


class RunRequest(BaseModel):
    service: str
    severity: str
    description: str
    source: str = "api"
    metadata: dict = {}
    agent_type: str = os.environ.get("AGENT_TYPE", "openrouter")
    model: str | None = None


class ReplayRequest(BaseModel):
    run_id: str
    replay_from: str
    alert: dict
    agent_type: str = os.environ.get("AGENT_TYPE", "openrouter")


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ops-runbook-harness"}


@app.get("/debug/discovery")
async def debug_discovery():
    result = {
        "cached": {},
        "allowed_services": _guardrails.config.allowed_services if _guardrails else [],
        "identity": None,
        "fresh_arns": [],
        "error": None,
    }
    try:
        from src.aws.discovery import get_service_instance_map
        result["cached"] = get_service_instance_map()
    except Exception as e:
        result["error"] = f"discovery import: {e}"
        return result
    try:
        import boto3
        sts = boto3.client("sts", region_name="us-east-2")
        r = sts.get_caller_identity()
        result["identity"] = {"Account": r.get("Account"), "Arn": r.get("Arn")}
    except Exception as e:
        result["identity"] = f"sts error: {e}"
    try:
        import boto3
        client = boto3.client("resourcegroupstaggingapi", region_name="us-east-2")
        paginator = client.get_paginator("get_resources")
        for page in paginator.paginate(TagFilters=[{"Key": "Monitor", "Values": ["true"]}], ResourceTypeFilters=["ec2:instance"]):
            for r in page["ResourceTagMappingList"]:
                result["fresh_arns"].append(r["ResourceARN"])
    except Exception as e:
        result["error"] = f"tagging api: {e}"
    return result


@app.post("/webhook/ec2")
async def webhook_ec2(event: dict):
    """
    Receive SNS notifications from EventBridge/CloudWatch and run the harness.

    Handles three cases:
    - SNS SubscriptionConfirmation: fetches the SubscribeURL to confirm
    - SNS Notification: unwraps the Message field to get the EventBridge event
    - Direct EventBridge JSON: used for manual testing
    """
    msg_type = event.get("Type")

    # SNS subscription handshake — fetch the SubscribeURL to confirm
    if msg_type == "SubscriptionConfirmation":
        subscribe_url = event.get("SubscribeURL")
        if subscribe_url:
            async with httpx.AsyncClient() as client:
                await client.get(subscribe_url)
            logger.info("SNS subscription confirmed")
        return {"status": "confirmed"}

    # SNS notification — unwrap to get the inner EventBridge event
    if msg_type == "Notification":
        import json as _json
        try:
            ec2_event = _json.loads(event.get("Message", "{}"))
        except Exception:
            raise HTTPException(status_code=422, detail="Could not parse SNS Message as JSON")
    else:
        ec2_event = event

    try:
        alert = await asyncio.to_thread(MaterialHandler.normalize_ec2_event, ec2_event)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    agent_type = os.environ.get("AGENT_TYPE", "openrouter")
    try:
        agent = _get_agent(agent_type)
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        registry = create_registry(_guardrails, service=alert.service)
        loop = HarnessLoop(agent=agent, guardrails=_guardrails, store=_store, registry=registry)
        result = await loop.run(alert)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Harness execution failed: {e}")


@app.get("/agents")
async def list_agents():
    """Return each agent with live reachability status."""
    agents = []

    # Ollama — probe the local API
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{ollama_url.rstrip('/v1')}/api/tags")
            available_models = [m["name"] for m in r.json().get("models", [])]
            agents.append({
                "id": "ollama",
                "label": f"Ollama — {ollama_model}",
                "model": ollama_model,
                "available": True,
                "status": "ready",
                "available_models": available_models,
            })
    except Exception as e:
        agents.append({
            "id": "ollama",
            "label": f"Ollama — {ollama_model}",
            "model": ollama_model,
            "available": False,
            "status": f"unreachable — is Ollama running? ({e})",
            "available_models": [],
        })

    # Claude — check for API key
    claude_model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    has_claude_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    agents.append({
        "id": "claude",
        "label": f"Claude — {claude_model}",
        "model": claude_model,
        "available": has_claude_key,
        "status": "ready" if has_claude_key else "ANTHROPIC_API_KEY not set",
    })

    # OpenAI — check for API key
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    has_openai_key = bool(os.environ.get("OPENAI_API_KEY"))
    agents.append({
        "id": "openai",
        "label": f"OpenAI — {openai_model}",
        "model": openai_model,
        "available": has_openai_key,
        "status": "ready" if has_openai_key else "OPENAI_API_KEY not set",
    })

    # OpenRouter — check for API key
    openrouter_model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
    has_openrouter_key = bool(os.environ.get("OPENROUTER_API_KEY"))
    agents.append({
        "id": "openrouter",
        "label": f"OpenRouter — {openrouter_model}",
        "model": openrouter_model,
        "available": has_openrouter_key,
        "status": "ready" if has_openrouter_key else "OPENROUTER_API_KEY not set",
    })

    # Mock — always available
    agents.append({
        "id": "mock",
        "label": "Mock (scripted, no model)",
        "model": None,
        "available": True,
        "status": "ready",
    })

    return {"agents": agents, "default": os.environ.get("AGENT_TYPE", "openrouter")}


@app.get("/runs")
async def list_runs(limit: int = 50):
    return await _store.list_runs(limit=min(limit, 100))


@app.post("/run")
async def run_harness(request: RunRequest):
    try:
        alert = MaterialHandler.validate_alert(request.model_dump(exclude={"agent_type", "model"}))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        agent = _get_agent(request.agent_type, request.model)
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        initial_state = request.metadata.get("_initial_state", "failed")
        registry = create_registry(_guardrails, service=alert.service, initial_state=initial_state)
        loop = HarnessLoop(agent=agent, guardrails=_guardrails, store=_store, registry=registry)
        result = await loop.run(alert)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Harness execution failed: {e}")


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
        raise HTTPException(status_code=400, detail=f"Invalid decision: {decision.decision}")


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

    agent = _get_agent(request.agent_type)
    registry = create_registry(_guardrails)
    loop = HarnessLoop(agent=agent, guardrails=_guardrails, store=_store, registry=registry)
    result = await loop.run(alert, replay_from=stage, replay_run_id=request.run_id)
    return result
