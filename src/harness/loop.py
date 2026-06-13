"""
Core agent loop.

State is derived entirely from observed tool calls and their outputs —
never from parsing model free text. This makes the loop model-agnostic:
any model that calls tools in a reasonable sequence will complete successfully.

Checkpoints:
- CP1: Alert valid (known service, well-formed)
- CP2: Data gathered (check_status or read_logs called; diagnosis synthesized from outputs)
- CP3: Remediation action allowed (evaluated against the actual tool called)
- CP4: Service recovered (post-remediation check_status output)

Terminals:
- Blocked tool → DESTRUCTIVE_ACTION_REQUESTED → AWAITING_HUMAN
- CP failure (CRITICAL severity) → AWAITING_HUMAN
- Turn/token limit → FAILED
- CP4 pass → COMPLETED
"""
import json
import uuid
from typing import Any

from src.agents.base import BaseAgent
from src.harness import metrics
from src.harness.alarms import AlarmManager
from src.harness.checkpoints import CheckpointManager
from src.harness.guardrails import GuardrailEngine
from src.harness.material import MaterialHandler
from src.harness.models import (
    Alert,
    AlarmType,
    CheckpointStage,
    GuardrailDecision,
    RunStatus,
)
from src.tools.registry import ToolRegistry
from src.db.store import CheckpointStore


SYSTEM_PROMPT = """You are an infrastructure operations agent. Diagnose and remediate service incidents using the tools available to you.

1. Call check_status and read_logs to understand what is wrong.
2. Call the appropriate remediation tool (restart_service, kill_query, or flush_dns).
3. Call check_status again to confirm the service has recovered.

Think step by step and explain your reasoning. The harness manages checkpoints and will close the run once recovery is confirmed."""

REMEDIATION_TOOLS = frozenset({"restart_service", "kill_query", "flush_dns"})
DATA_TOOLS = frozenset({"check_status", "read_logs"})


def _synthesize_diagnosis(status_output: dict | None, log_output: dict | None, alert: Alert) -> dict:
    """Build a diagnosis dict from actual tool outputs, not model text."""
    evidence = []
    indicators = []

    if status_output:
        svc_status = status_output.get("status", "unknown")
        if svc_status in ("degraded", "critical", "warning"):
            indicators.append(f"service status={svc_status}")
        for k, v in status_output.items():
            if k not in ("service", "status"):
                evidence.append(f"{k}={v}")

    if log_output:
        for line in log_output.get("log_lines", []):
            if "ERROR" in line or "WARN" in line:
                evidence.append(line.split("] ", 1)[-1] if "] " in line else line)

    hypothesis = (
        f"{alert.service} incident — {'; '.join(indicators)}"
        if indicators
        else f"{alert.service} incident — {alert.description[:120]}"
    )
    confidence = 0.85 if (status_output and log_output) else 0.70

    return {"hypothesis": hypothesis, "confidence": confidence, "evidence": evidence[:6]}


class HarnessLoop:
    def __init__(
        self,
        agent: BaseAgent,
        guardrails: GuardrailEngine,
        store: CheckpointStore,
        registry: ToolRegistry,
    ):
        self.agent = agent
        self.guardrails = guardrails
        self.store = store
        self.registry = registry
        self.alarm_manager = AlarmManager(
            severity_overrides=guardrails.config.severity_overrides
        )
        self.checkpoint_manager = CheckpointManager(store, guardrails)

    def _emit_alarm(self, alarm_type: AlarmType, context: dict, recommended_action: str) -> bool:
        should_halt = self.alarm_manager.emit(
            alarm_type, context=context, recommended_action=recommended_action
        )
        alarms = self.alarm_manager.get_alarms()
        if alarms:
            metrics.alarm_emitted(alarm_type.value, alarms[-1].severity.value)
        return should_halt

    async def run(
        self,
        alert: Alert,
        replay_from: CheckpointStage | None = None,
        replay_run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        await self.store.create_run(run_id, alert.alert_id)
        messages: list[dict] = []

        # ---- CP1: Validate alert ----
        if replay_from and replay_from != CheckpointStage.CP1_ALERT_PARSED and replay_run_id:
            cp1_state = await self.checkpoint_manager.load_replay_state(
                replay_run_id, CheckpointStage.CP1_ALERT_PARSED
            )
            if cp1_state is None:
                return await self._fail(run_id, "Replay failed: CP1 state not found")
        else:
            cp1 = await self.checkpoint_manager.evaluate_cp1(run_id, alert.model_dump())
            metrics.checkpoint_evaluated(CheckpointStage.CP1_ALERT_PARSED.value, cp1.passed)
            if not cp1.passed:
                should_halt = self._emit_alarm(
                    AlarmType.UNKNOWN_SERVICE,
                    context={"alert": alert.model_dump(), "reason": cp1.failure_reason},
                    recommended_action="Escalate to on-call engineer — unknown service",
                )
                if should_halt:
                    return await self._escalate(run_id, alert, messages)
                return await self._fail(run_id, cp1.failure_reason or "CP1 failed", alert, messages)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"INCIDENT ALERT:\n{json.dumps(alert.model_dump(), indent=2, default=str)}"},
        ]
        tools = self.registry.get_tool_schemas()

        actions_taken: list[dict] = []
        metrics_before: dict = {}
        metrics_after: dict = {}
        diagnosis: dict | None = None
        cp2_evaluated = False
        cp3_evaluated = False
        remediation_idx: int | None = None
        turn = 0
        total_tokens = 0

        while turn < self.guardrails.config.max_turns:
            turn += 1

            within_limits, violation = self.guardrails.check_limits(turn, total_tokens)
            if not within_limits:
                self._emit_alarm(
                    AlarmType.TURN_LIMIT_REACHED,
                    context={"turn": turn, "tokens": total_tokens, "reason": violation},
                    recommended_action="Review agent progress and decide whether to continue",
                )
                return await self._fail(run_id, violation or "Limits exceeded", alert, messages)

            response = await self.agent.run(messages, tools)
            total_tokens += sum(response.usage.values())
            messages.append({
                "role": "assistant",
                "content": response.text or "",
                "tool_calls_made": [tc.model_dump() for tc in response.tool_calls],
            })

            if not response.tool_calls:
                if remediation_idx is None:
                    prompt = "Call check_status and read_logs to gather data, then call the appropriate remediation tool."
                else:
                    prompt = f"Call check_status on '{alert.service}' to verify the service has recovered."
                messages.append({"role": "user", "content": prompt})
                continue

            # ---- Execute tool calls ----
            for tc in response.tool_calls:
                decision = self.guardrails.check_action(tc.tool_name)
                if decision == GuardrailDecision.BLOCKED:
                    self._emit_alarm(
                        AlarmType.DESTRUCTIVE_ACTION_REQUESTED,
                        context={"tool": tc.tool_name, "args": tc.arguments},
                        recommended_action=f"'{tc.tool_name}' is not on the approved list. Review and approve manually.",
                    )
                    return await self._escalate(run_id, alert, messages)
                if decision == GuardrailDecision.NEEDS_APPROVAL:
                    self._emit_alarm(
                        AlarmType.DESTRUCTIVE_ACTION_REQUESTED,
                        context={"tool": tc.tool_name, "args": tc.arguments},
                        recommended_action=f"'{tc.tool_name}' requires human approval before execution.",
                    )
                    return await self._escalate(run_id, alert, messages)

                result = await self.registry.execute(tc.tool_name, tc.arguments)
                metrics.tool_executed(tc.tool_name, result.success)
                actions_taken.append({"tool": tc.tool_name, "args": tc.arguments, "result": result.model_dump()})
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result.model_dump(), default=str),
                    "tool_name": tc.tool_name,
                })

                if tc.tool_name == "check_status" and result.success:
                    if not metrics_before:
                        metrics_before = result.output
                    else:
                        metrics_after = result.output

            # ---- Phase transitions derived from actions_taken ----
            tools_called = {a["tool"] for a in actions_taken}
            remediation_idx = next(
                (i for i, a in enumerate(actions_taken) if a["tool"] in REMEDIATION_TOOLS), None
            )

            # After remediation fires, demand a verification check_status — don't let the agent wander
            just_remediated = (
                remediation_idx is not None
                and actions_taken[-1]["tool"] in REMEDIATION_TOOLS
            )
            if just_remediated:
                messages.append({
                    "role": "user",
                    "content": f"Remediation executed. Call check_status on '{alert.service}' now to verify recovery.",
                })
                continue

            # CP2: synthesize diagnosis from actual tool outputs (once, as soon as we have data)
            if not cp2_evaluated and tools_called & DATA_TOOLS:
                cp2_evaluated = True
                status_out = next(
                    (a["result"].get("output", {}) for a in actions_taken if a["tool"] == "check_status"), None
                )
                log_out = next(
                    (a["result"].get("output", {}) for a in actions_taken if a["tool"] == "read_logs"), None
                )
                diagnosis = _synthesize_diagnosis(status_out, log_out, alert)
                cp2 = await self.checkpoint_manager.evaluate_cp2(run_id, diagnosis)
                metrics.checkpoint_evaluated(CheckpointStage.CP2_HYPOTHESIS_FORMED.value, cp2.passed)
                if not cp2.passed:
                    self._emit_alarm(
                        AlarmType.CONFIDENCE_LOW,
                        context={"diagnosis": diagnosis, "reason": cp2.failure_reason},
                        recommended_action="Low confidence — gather more data before remediating.",
                    )
                    messages.append({
                        "role": "user",
                        "content": "Confidence is too low. Gather more data before proceeding to remediation.",
                    })
                    continue

            # CP3: validate the actual remediation tool called (once)
            if remediation_idx is not None and not cp3_evaluated:
                cp3_evaluated = True
                remediation_tool = actions_taken[remediation_idx]["tool"]
                cp3 = await self.checkpoint_manager.evaluate_cp3(run_id, [remediation_tool])
                metrics.checkpoint_evaluated(CheckpointStage.CP3_PLAN_VALIDATED.value, cp3.passed)
                if not cp3.passed:
                    self._emit_alarm(
                        AlarmType.DESTRUCTIVE_ACTION_REQUESTED,
                        context={"tool": remediation_tool, "blocked": cp3.state.get("blocked", [])},
                        recommended_action="Remediation action is not on the approved list.",
                    )
                    return await self._escalate(run_id, alert, messages)

            # CP4: post-remediation check_status received — evaluate and complete
            if remediation_idx is not None:
                post_checks = [
                    a for a in actions_taken[remediation_idx + 1:]
                    if a["tool"] == "check_status"
                ]
                if post_checks:
                    health_data = post_checks[-1]["result"].get("output", {})
                    cp4 = await self.checkpoint_manager.evaluate_cp4(run_id, health_data)
                    metrics.checkpoint_evaluated(CheckpointStage.CP4_HEALTH_CHECK.value, cp4.passed)
                    if not cp4.passed:
                        self._emit_alarm(
                            AlarmType.REMEDIATION_FAILED,
                            context={"health": health_data, "reason": cp4.failure_reason},
                            recommended_action="Remediation did not restore service health. Escalate immediately.",
                        )
                        return await self._escalate(run_id, alert, messages)

                    remediation_tool = actions_taken[remediation_idx]["tool"]
                    summary = (
                        response.text
                        or f"Remediation via {remediation_tool} completed. "
                           f"Post-check status: {health_data.get('status', 'unknown')}."
                    )
                    report = MaterialHandler.build_report(
                        run_id=run_id,
                        alert=alert,
                        diagnosis=diagnosis["hypothesis"] if diagnosis else "",
                        actions_taken=actions_taken,
                        outcomes=[summary],
                        metrics_before=metrics_before,
                        metrics_after=metrics_after,
                        downstream_effects=[],
                        resolution_status="resolved",
                        alarms=self.alarm_manager.get_alarms(),
                        checkpoints=self.checkpoint_manager.results,
                    )
                    metrics.run_completed(run_id, turn, total_tokens)
                    result = {
                        "run_id": run_id,
                        "status": RunStatus.COMPLETED.value,
                        "agent": self.agent.agent_name,
                        "report": report.model_dump(),
                        "alarms": [a.model_dump() for a in self.alarm_manager.get_alarms()],
                        "checkpoints": [c.model_dump() for c in self.checkpoint_manager.results],
                        "trace": [m for m in messages if m.get("role") != "system"],
                    }
                    await self.store.update_run_status(
                        run_id, RunStatus.COMPLETED.value, json.dumps(result, default=str)
                    )
                    return result

        self._emit_alarm(
            AlarmType.TURN_LIMIT_REACHED,
            context={"turn": turn, "tokens": total_tokens},
            recommended_action="Agent did not resolve within turn limit",
        )
        return await self._fail(run_id, "Turn limit reached", alert, messages)

    async def _fail(self, run_id: str, reason: str, alert: Alert | None = None, messages: list | None = None) -> dict:
        metrics.run_failed(run_id)
        result = {
            "run_id": run_id,
            "status": RunStatus.FAILED.value,
            "agent": self.agent.agent_name,
            "error": reason,
            "report": {"alert": alert.model_dump()} if alert else None,
            "alarms": [a.model_dump() for a in self.alarm_manager.get_alarms()],
            "checkpoints": [c.model_dump() for c in self.checkpoint_manager.results],
            "trace": [m for m in (messages or []) if m.get("role") != "system"],
        }
        await self.store.update_run_status(run_id, RunStatus.FAILED.value, json.dumps(result, default=str))
        return result

    async def _escalate(self, run_id: str, alert: Alert | None = None, messages: list | None = None) -> dict:
        metrics.run_awaiting_human(run_id)
        critical_alarms = [a for a in self.alarm_manager.get_alarms() if a.severity.value == "CRITICAL"]
        result = {
            "run_id": run_id,
            "status": RunStatus.AWAITING_HUMAN.value,
            "agent": self.agent.agent_name,
            "escalation": {
                "reason": critical_alarms[-1].recommended_action if critical_alarms else "Unknown",
                "alarm": critical_alarms[-1].model_dump() if critical_alarms else None,
            },
            "report": {"alert": alert.model_dump()} if alert else None,
            "alarms": [a.model_dump() for a in self.alarm_manager.get_alarms()],
            "checkpoints": [c.model_dump() for c in self.checkpoint_manager.results],
            "trace": [m for m in (messages or []) if m.get("role") != "system"],
        }
        await self.store.update_run_status(run_id, RunStatus.AWAITING_HUMAN.value, json.dumps(result, default=str))
        return result
