"""
Core agent loop.

The agent drives phase transitions by emitting structured JSON in its text
responses. Tool calls populate metrics; text responses advance checkpoints.

Phases (all detected via _extract_json on agent text):
  1. Agent calls check_status / read_logs → metrics_before captured
  2. Agent emits {"diagnosis": {"hypothesis", "confidence", "evidence"}} → CP2
  3. Agent emits {"plan": {"actions": [...], "rationale": ...}}           → CP3
  4. Agent may call tools again; any check_status → metrics_after
  5. Agent emits {"resolution": {"status", "summary"}}                    → CP4

Terminals:
  - Blocked tool → DESTRUCTIVE_ACTION_REQUESTED → AWAITING_HUMAN
  - CP2 low confidence → CONFIDENCE_LOW alarm; agent prompted to gather more data
  - CP3 blocked actions → DESTRUCTIVE_ACTION_REQUESTED → AWAITING_HUMAN
  - CP4 fail (degraded metrics_after) → REMEDIATION_FAILED → AWAITING_HUMAN
  - CP4 pass → COMPLETED
  - Turn/token limit → FAILED
"""
import json
import re
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


SYSTEM_PROMPT = """You are an infrastructure operations agent. Diagnose and remediate service incidents.

Work through these steps and emit structured JSON at each phase:

1. Call check_status and read_logs to gather data.
2. Emit your diagnosis:
   {"diagnosis": {"hypothesis": "...", "confidence": 0.0-1.0, "evidence": ["..."]}}
3. Emit your remediation plan:
   {"plan": {"actions": ["restart_service", ...], "rationale": "..."}}
4. Execute the plan (call restart_service, kill_query, or flush_dns). Optionally call check_status again to confirm recovery.
5. Emit your resolution:
   {"resolution": {"status": "resolved", "summary": "..."}}

Confidence must be >= 0.7 to proceed. The harness validates each step."""


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

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract a JSON object from text — from a ```json block or as bare JSON."""
        if not text:
            return None
        # Try ```json code block first
        m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # Fall back to first {...} in the text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None

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
                    if cp2_evaluated:
                        metrics_after = result.output

            # ---- Text-driven phase transitions ----
            parsed = self._extract_json(response.text or "")
            if parsed:
                # CP2: diagnosis
                if not cp2_evaluated and "diagnosis" in parsed:
                    cp2_evaluated = True
                    diag = parsed["diagnosis"]
                    diagnosis = {
                        "hypothesis": diag.get("hypothesis", ""),
                        "confidence": float(diag.get("confidence", 0.0)),
                        "evidence": diag.get("evidence", []),
                    }
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
                            "content": "Confidence is too low. Call check_status and read_logs to gather more data before emitting a diagnosis.",
                        })
                        continue

                # CP3: plan
                if cp2_evaluated and not cp3_evaluated and "plan" in parsed:
                    cp3_evaluated = True
                    planned_actions = parsed["plan"].get("actions", [])
                    cp3 = await self.checkpoint_manager.evaluate_cp3(run_id, planned_actions)
                    metrics.checkpoint_evaluated(CheckpointStage.CP3_PLAN_VALIDATED.value, cp3.passed)
                    if not cp3.passed:
                        self._emit_alarm(
                            AlarmType.DESTRUCTIVE_ACTION_REQUESTED,
                            context={"planned_actions": planned_actions, "blocked": cp3.state.get("blocked", [])},
                            recommended_action="Remediation action is not on the approved list.",
                        )
                        return await self._escalate(run_id, alert, messages)

                # CP4: resolution
                if cp2_evaluated and cp3_evaluated and "resolution" in parsed:
                    health_data = metrics_after if metrics_after else {"status": "healthy"}
                    cp4 = await self.checkpoint_manager.evaluate_cp4(run_id, health_data)
                    metrics.checkpoint_evaluated(CheckpointStage.CP4_HEALTH_CHECK.value, cp4.passed)
                    if not cp4.passed:
                        self._emit_alarm(
                            AlarmType.REMEDIATION_FAILED,
                            context={"health": health_data, "reason": cp4.failure_reason},
                            recommended_action="Remediation did not restore service health. Escalate immediately.",
                        )
                        return await self._escalate(run_id, alert, messages)

                    summary = parsed["resolution"].get("summary", "Remediation completed.")
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

            # No tool calls and no actionable JSON — prompt the agent forward
            if not response.tool_calls and not parsed:
                if not cp2_evaluated:
                    messages.append({
                        "role": "user",
                        "content": "Call check_status and read_logs to gather data, then emit your diagnosis JSON.",
                    })
                elif not cp3_evaluated:
                    messages.append({
                        "role": "user",
                        "content": "Emit your plan JSON with the actions you will take.",
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": "Execute your plan, then emit your resolution JSON.",
                    })

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
