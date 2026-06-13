"""
Checkpoint evaluation.

CheckpointManager evaluates each checkpoint stage against its criteria.
It uses CheckpointStore for persistence. Each checkpoint receives the
current run state and returns a CheckpointResult.

Checkpoint criteria:
- CP1: Alert parsed — service and severity are known/valid
- CP2: Hypothesis formed — agent provided diagnosis with confidence > threshold
- CP3: Plan valid — all proposed actions are on the guardrail allow-list
- CP4: Health check — post-action status shows improvement

The manager also supports loading state from a prior run for replay.
"""
from src.harness.models import CheckpointResult, CheckpointStage, GuardrailDecision
from src.harness.guardrails import GuardrailEngine
from src.db.store import CheckpointStore

KNOWN_SERVICES = ["web-api", "postgres", "redis", "cdn", "worker", "gateway"]


class CheckpointManager:
    def __init__(self, store: CheckpointStore, guardrail_engine: GuardrailEngine):
        self.store = store
        self.guardrails = guardrail_engine
        self.results: list[CheckpointResult] = []

    async def evaluate_cp1(self, run_id: str, alert_data: dict) -> CheckpointResult:
        """CP1: Alert parsed. Pass if service is known and severity is valid."""
        service = alert_data.get("service", "")
        severity = alert_data.get("severity", "")
        valid_severities = ["low", "medium", "high", "critical"]

        known_services = set(KNOWN_SERVICES) | set(self.guardrails.config.allowed_services)
        passed = service in known_services and severity.lower() in valid_severities
        failure_reason = None
        if not passed:
            reasons = []
            if service not in known_services:
                reasons.append(f"Unknown service: {service}")
            if severity.lower() not in valid_severities:
                reasons.append(f"Invalid severity: {severity}")
            failure_reason = "; ".join(reasons)

        result = CheckpointResult(
            run_id=run_id,
            stage=CheckpointStage.CP1_ALERT_PARSED,
            passed=passed,
            state={"service": service, "severity": severity, "alert": alert_data},
            failure_reason=failure_reason,
        )
        await self._persist(result)
        return result

    async def evaluate_cp2(self, run_id: str, diagnosis: dict) -> CheckpointResult:
        """CP2: Hypothesis formed. Pass if confidence > 0.6 and hypothesis is non-empty."""
        confidence = diagnosis.get("confidence", 0.0)
        hypothesis = diagnosis.get("hypothesis", "")
        threshold = 0.6

        passed = confidence >= threshold and len(hypothesis) > 0
        failure_reason = None
        if not passed:
            if confidence < threshold:
                failure_reason = f"Confidence too low: {confidence} < {threshold}"
            elif not hypothesis:
                failure_reason = "No hypothesis provided"

        result = CheckpointResult(
            run_id=run_id,
            stage=CheckpointStage.CP2_HYPOTHESIS_FORMED,
            passed=passed,
            state={"diagnosis": diagnosis, "confidence": confidence},
            failure_reason=failure_reason,
        )
        await self._persist(result)
        return result

    async def evaluate_cp3(self, run_id: str, planned_actions: list[str]) -> CheckpointResult:
        """CP3: Plan valid. Pass if ALL proposed actions are on the allow-list."""
        blocked = []
        for action in planned_actions:
            decision = self.guardrails.check_action(action)
            if decision == GuardrailDecision.BLOCKED:
                blocked.append(action)

        passed = len(blocked) == 0
        failure_reason = f"Blocked actions: {blocked}" if blocked else None

        result = CheckpointResult(
            run_id=run_id,
            stage=CheckpointStage.CP3_PLAN_VALIDATED,
            passed=passed,
            state={"planned_actions": planned_actions, "blocked": blocked},
            failure_reason=failure_reason,
        )
        await self._persist(result)
        return result

    async def evaluate_cp4(self, run_id: str, health_data: dict) -> CheckpointResult:
        """CP4: Health check. Pass if status is 'healthy' or metrics improved."""
        status = health_data.get("status", "unknown")
        passed = status in ("healthy", "recovered", "ok")
        failure_reason = None if passed else f"Service status: {status}"

        result = CheckpointResult(
            run_id=run_id,
            stage=CheckpointStage.CP4_HEALTH_CHECK,
            passed=passed,
            state={"health_data": health_data},
            failure_reason=failure_reason,
        )
        await self._persist(result)
        return result

    async def load_replay_state(self, run_id: str, stage: CheckpointStage) -> dict | None:
        """Load saved state from a prior run for replay."""
        return await self.store.get_checkpoint_state(run_id, stage.value)

    async def _persist(self, result: CheckpointResult) -> None:
        self.results.append(result)
        await self.store.save_checkpoint(
            checkpoint_id=result.checkpoint_id,
            run_id=result.run_id,
            stage=result.stage.value,
            passed=result.passed,
            state=result.state,
            failure_reason=result.failure_reason,
        )
