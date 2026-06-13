import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock

from src.api.routes import app
from src.db.store import CheckpointStore
from src.harness.guardrails import GuardrailConfig, GuardrailEngine
from src.harness.models import AgentResponse, RunStatus, ToolCall


# Happy-path mock agent responses
HAPPY_RESPONSES = [
    AgentResponse(tool_calls=[ToolCall(tool_name="check_status", arguments={"service": "redis"})]),
    AgentResponse(tool_calls=[ToolCall(tool_name="read_logs", arguments={"service": "web-api"})]),
    AgentResponse(text='{"diagnosis": {"hypothesis": "CPU issue", "confidence": 0.9, "evidence": ["logs"]}}'),
    AgentResponse(text='{"plan": {"actions": ["check_status", "read_logs"], "rationale": "verify"}}'),
    AgentResponse(text='{"resolution": {"status": "resolved", "summary": "Fixed"}}'),
]


@pytest.fixture
async def client():
    store = CheckpointStore(db_path=":memory:")
    await store.connect()
    config = GuardrailConfig(
        allowed_actions=["check_status", "restart_service", "read_logs", "kill_query", "flush_dns"],
        requires_approval=["restart_service", "kill_query"],
        max_turns=15,
        token_budget=50000,
    )
    guardrails = GuardrailEngine(config)

    import src.api.routes as routes_module
    routes_module._store = store
    routes_module._guardrails = guardrails

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await store.close()


# 1. GET /health → 200
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# 2. POST /run with valid alert → 200 (mock agent)
async def test_run_valid_alert(client):
    from tests.test_loop import MockAgent

    call_count = 0

    async def mock_run(messages, tools):
        nonlocal call_count
        resp = HAPPY_RESPONSES[min(call_count, len(HAPPY_RESPONSES) - 1)]
        call_count += 1
        return resp

    mock_agent = MockAgent(HAPPY_RESPONSES)

    with patch("src.api.routes._get_agent", return_value=mock_agent):
        resp = await client.post("/run", json={
            "service": "web-api",
            "severity": "high",
            "description": "CPU spiking",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == RunStatus.COMPLETED.value


# 3. POST /run with missing service → 422
async def test_run_missing_service(client):
    resp = await client.post("/run", json={
        "severity": "high",
        "description": "no service here",
    })
    assert resp.status_code == 422


# 4. GET /runs/{run_id} for existing run → 200 with checkpoints
async def test_get_run_exists(client):
    from tests.test_loop import MockAgent

    mock_agent = MockAgent(HAPPY_RESPONSES)
    with patch("src.api.routes._get_agent", return_value=mock_agent):
        run_resp = await client.post("/run", json={
            "service": "web-api",
            "severity": "high",
            "description": "CPU spiking",
        })
    run_id = run_resp.json()["run_id"]

    resp = await client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert "checkpoints" in data


# 5. GET /runs/{run_id} for non-existent run → 404
async def test_get_run_not_found(client):
    resp = await client.get("/runs/nonexistent-run-id")
    assert resp.status_code == 404


# 6. POST /runs/{run_id}/escalation approve on AWAITING_HUMAN run → 200
async def test_escalation_approve(client):
    import src.api.routes as routes_module
    store = routes_module._store

    # Create a run in AWAITING_HUMAN status
    await store.create_run("esc-run-1", "alert-1")
    await store.update_run_status("esc-run-1", "AWAITING_HUMAN")

    resp = await client.post("/runs/esc-run-1/escalation", json={
        "decision": "approve",
        "reason": "looks ok",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["decision"] == "approved"


# 7. POST /runs/{run_id}/escalation on non-AWAITING_HUMAN run → 400
async def test_escalation_wrong_status(client):
    import src.api.routes as routes_module
    store = routes_module._store

    await store.create_run("completed-run-1", "alert-2")
    await store.update_run_status("completed-run-1", "COMPLETED")

    resp = await client.post("/runs/completed-run-1/escalation", json={
        "decision": "approve",
        "reason": "",
    })
    assert resp.status_code == 400


# 8. POST /webhook/ec2 — SNS SubscriptionConfirmation triggers GET on SubscribeURL
async def test_webhook_sns_subscription_confirmation(client):
    subscribe_url = "https://sns.amazonaws.com/confirm?token=abc123"
    payload = json.dumps({
        "Type": "SubscriptionConfirmation",
        "SubscribeURL": subscribe_url,
        "TopicArn": "arn:aws:sns:us-east-2:123456789012:ec2-alerts",
    })

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_http

        resp = await client.post(
            "/webhook/ec2",
            content=payload,
            headers={"Content-Type": "text/plain"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "confirmed"}
    mock_http.get.assert_awaited_once_with(subscribe_url)


# 9. POST /webhook/ec2 — SNS Notification unwraps inner event and runs harness
async def test_webhook_sns_notification(client):
    from tests.test_loop import MockAgent

    ec2_event = {
        "source": "aws.ec2",
        "detail-type": "EC2 Instance State-change Notification",
        "detail": {"instance-id": "i-0abc123", "state": "stopped"},
        "region": "us-east-2",
    }
    sns_payload = json.dumps({
        "Type": "Notification",
        "Message": json.dumps(ec2_event),
        "TopicArn": "arn:aws:sns:us-east-2:123456789012:ec2-alerts",
    })

    mock_agent = MockAgent(HAPPY_RESPONSES)
    with patch("src.api.routes._get_agent", return_value=mock_agent):
        resp = await client.post(
            "/webhook/ec2",
            content=sns_payload,
            headers={"Content-Type": "text/plain"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data


# 10. POST /webhook/ec2 — direct EventBridge JSON (no SNS envelope)
async def test_webhook_direct_eventbridge(client):
    from tests.test_loop import MockAgent

    ec2_event = {
        "source": "aws.ec2",
        "detail-type": "EC2 Instance State-change Notification",
        "detail": {"instance-id": "i-0abc123", "state": "stopped"},
        "region": "us-east-2",
    }

    mock_agent = MockAgent(HAPPY_RESPONSES)
    with patch("src.api.routes._get_agent", return_value=mock_agent):
        resp = await client.post("/webhook/ec2", json=ec2_event)

    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data


# 11. POST /webhook/ec2 — malformed body → 422
async def test_webhook_malformed_body(client):
    resp = await client.post(
        "/webhook/ec2",
        content=b"not json at all",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code == 422
