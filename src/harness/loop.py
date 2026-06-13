"""
Core agent loop.

The loop drives an agent through the incident remediation workflow:
  1. Validate alert (CP1)
  2. Agent diagnoses (CP2)
  3. Agent plans remediation (CP3)
  4. Execute remediation + health check (CP4)

Each step checks guardrails before tool execution, evaluates checkpoints,
and emits alarms when things go wrong. The loop never imports agent-specific
code — it uses the BaseAgent interface.

Key behaviors:
- Blocked actions → DESTRUCTIVE_ACTION_REQUESTED alarm → halt
- Turn limit → TURN_LIMIT_REACHED alarm → halt
- CRITICAL alarm → AWAITING_HUMAN status → halt (HITL)
- CP failure → appropriate alarm → halt or continue based on severity
"""
import json
import uuid
from typing import Any

from src.agents.base import BaseAgent
from src.harness.alarms import AlarmManager
from src.harness.checkpoints import CheckpointManager
from src.harness.guardrails import GuardrailEngine
from src.harness.material import MaterialHandler
from src.harness.models import (
    AgentResponse,
    Alert,
    AlarmType,
    CheckpointStage,
    GuardrailDecision,
    RemediationReport,
    RunStatus,
    ToolCall,
)
from src.tools.registry import ToolRegistry
from src.db.store import CheckpointStore


SYSTEM_PROMPT = """You are an infrastructure operations agent. Your job is to diagnose and remediate service incidents using the tools available to you.

WORKFLOW:
1. DIAGNOSE: Use check_status and read_logs to understand the problem. Form a hypothesis about the root cause.
2. PLAN: Decide which remediation action to take. Only use tools that are available to you.
3. EXECUTE: Run the remediation action.
4. VERIFY: Use check_status again to confirm the fix worked.

RULES:
- Only use the tools provided. Do not suggest actions you cannot take.
- If a tool call is blocked, choose a different approach or escalate.
- Always verify your fix worked with a health check after remediation.
- Be concise in your reasoning.

When you have completed diagnosis, respond with a JSON block:
{"diagnosis": {"hypothesis": "...", "confidence": 0.0-1.0, "evidence": ["..."]}}

When you have a remediation plan, respond with a JSON block:
{"plan": {"actions": ["tool_name_1", "tool_name_2"], "rationale": "..."}}

When remediation is complete and verified, respond with a JSON block:
{"resolution": {"status": "resolved", "summary": "...", "actions_taken": [{"tool": "...", "result": "..."}]}}
"""


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

    async def run(
        self,
        alert: Alert,
        replay_from: CheckpointStage | None = None,
        replay_run_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute the full harness loop for an alert.

        Returns a dict with:
        - run_id: str
        - status: RunStatus value
        - report: RemediationReport (if resolved) or None
        - alarms: list of Alarm dicts
        - checkpoints: list of CheckpointResult dicts
        - escalation: dict with alarm context (if AWAITING_HUMAN)
        """
        run_id = str(uuid.uuid4())
        await self.store.create_run(run_id, alert.alert_id)

        # ---- CP1: Validate alert ----
        if replay_from and replay_from != CheckpointStage.CP1_ALERT_PARSED and replay_run_id:
            cp1_state = await self.checkpoint_manager.load_replay_state(
                replay_run_id, CheckpointStage.CP1_ALERT_PARSED
            )
            if cp1_state is None:
                return await self._fail(run_id, "Replay failed: CP1 state not found")
        else:
            cp1 = await self.checkpoint_manager.evaluate_cp1(run_id, alert.model_dump())
            if not cp1.passed:
                should_halt = self.alarm_manager.emit(
                    AlarmType.UNKNOWN_SERVICE,
                    context={"alert": alert.model_dump(), "reason": cp1.failure_reason},
                    recommended_action="Escalate to on-call engineer — unknown service",
                )
                if should_halt:
                    return await self._escalate(run_id)
                return await self._fail(run_id, cp1.failure_reason or "CP1 failed")

        # ---- Agent diagnosis loop (CP2) ----
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"INCIDENT ALERT:\n{json.dumps(alert.model_dump(), indent=2, default=str)}"},
        ]
        tools = self.registry.get_tool_schemas()

        diagnosis = None
        plan = None
        actions_taken = []
        metrics_before = {}
        metrics_after = {}
        turn = 0
        total_tokens = 0

        while turn < self.guardrails.config.max_turns:
            turn += 1

            within_limits, violation = self.guardrails.check_limits(turn, total_tokens)
            if not within_limits:
                self.alarm_manager.emit(
                    AlarmType.TURN_LIMIT_REACHED,
                    context={"turn": turn, "tokens": total_tokens, "reason": violation},
                    recommended_action="Review agent progress and decide whether to continue",
                )
                return await self._fail(run_id, violation or "Limits exceeded")

            response = await self.agent.run(messages, tools)
            total_tokens += sum(response.usage.values())
            messages.append({"role": "assistant", "content": response.text or "", "tool_calls_made": [tc.model_dump() for tc in response.tool_calls]})

            # Process tool calls
            if response.tool_calls:
                for tc in response.tool_calls:
                    decision = self.guardrails.check_action(tc.tool_name)
                    if decision == GuardrailDecision.BLOCKED:
                        self.alarm_manager.emit(
                            AlarmType.DESTRUCTIVE_ACTION_REQUESTED,
                            context={"tool": tc.tool_name, "args": tc.arguments},
                            recommended_action=f"Action '{tc.tool_name}' is not on the approved list. Review and approve manually.",
                        )
                        return await self._escalate(run_id)

                    result = await self.registry.execute(tc.tool_name, tc.arguments)
                    actions_taken.append({"tool": tc.tool_name, "args": tc.arguments, "result": result.model_dump()})
                    messages.append({"role": "tool", "content": json.dumps(result.model_dump(), default=str), "tool_name": tc.tool_name})

                    # Capture metrics from check_status calls
                    if tc.tool_name == "check_status" and result.success:
                        if not metrics_before:
                            metrics_before = result.output
                        else:
                            metrics_after = result.output
                continue

            # Parse structured responses from agent text
            if response.text:
                parsed = self._extract_json(response.text)
                if parsed:
                    if "diagnosis" in parsed and diagnosis is None:
                        diagnosis = parsed["diagnosis"]
                        cp2 = await self.checkpoint_manager.evaluate_cp2(run_id, diagnosis)
                        if not cp2.passed:
                            self.alarm_manager.emit(
                                AlarmType.CONFIDENCE_LOW,
                                context={"diagnosis": diagnosis, "reason": cp2.failure_reason},
                                recommended_action="Agent confidence is low. Consider providing additional context.",
                            )
                            messages.append({"role": "user", "content": "Your confidence is too low. Please gather more evidence using the available tools before forming a diagnosis."})
                            continue

                    if "plan" in parsed and plan is None:
                        plan = parsed["plan"]
                        planned_actions = plan.get("actions", [])
                        cp3 = await self.checkpoint_manager.evaluate_cp3(run_id, planned_actions)
                        if not cp3.passed:
                            self.alarm_manager.emit(
                                AlarmType.DESTRUCTIVE_ACTION_REQUESTED,
                                context={"plan": plan, "blocked": cp3.state.get("blocked", [])},
                                recommended_action="Plan contains blocked actions. Review and approve manually.",
                            )
                            return await self._escalate(run_id)
                        messages.append({"role": "user", "content": "Plan approved. Execute the remediation actions now."})
                        continue

                    if "resolution" in parsed:
                        # ---- CP4: Health check ----
                        health_data = metrics_after if metrics_after else {"status": "healthy"}
                        cp4 = await self.checkpoint_manager.evaluate_cp4(run_id, health_data)
                        if not cp4.passed:
                            self.alarm_manager.emit(
                                AlarmType.REMEDIATION_FAILED,
                                context={"health": health_data, "reason": cp4.failure_reason},
                                recommended_action="Remediation did not restore service health. Escalate immediately.",
                            )
                            return await self._escalate(run_id)

                        resolution = parsed["resolution"]
                        report = MaterialHandler.build_report(
                            run_id=run_id,
                            alert=alert,
                            diagnosis=diagnosis.get("hypothesis", "") if diagnosis else "",
                            actions_taken=actions_taken,
                            outcomes=[resolution.get("summary", "Resolved")],
                            metrics_before=metrics_before,
                            metrics_after=metrics_after,
                            downstream_effects=[],
                            resolution_status=resolution.get("status", "resolved"),
                            alarms=self.alarm_manager.get_alarms(),
                            checkpoints=self.checkpoint_manager.results,
                        )
                        await self.store.update_run_status(run_id, RunStatus.COMPLETED.value, report.model_dump_json())
                        return {
                            "run_id": run_id,
                            "status": RunStatus.COMPLETED.value,
                            "report": report.model_dump(),
                            "alarms": [a.model_dump() for a in self.alarm_manager.get_alarms()],
                            "checkpoints": [c.model_dump() for c in self.checkpoint_manager.results],
                        }

            # If agent returned text but no structured output and no tool calls, prompt it
            if not response.tool_calls:
                messages.append({"role": "user", "content": "Please continue with your diagnosis using the available tools, or provide your findings in the required JSON format."})

        # Fell through — turn limit
        self.alarm_manager.emit(
            AlarmType.TURN_LIMIT_REACHED,
            context={"turn": turn, "tokens": total_tokens},
            recommended_action="Agent did not resolve within turn limit",
        )
        return await self._fail(run_id, "Turn limit reached")

    async def _fail(self, run_id: str, reason: str) -> dict:
        await self.store.update_run_status(run_id, RunStatus.FAILED.value)
        return {
            "run_id": run_id,
            "status": RunStatus.FAILED.value,
            "error": reason,
            "alarms": [a.model_dump() for a in self.alarm_manager.get_alarms()],
            "checkpoints": [c.model_dump() for c in self.checkpoint_manager.results],
        }

    async def _escalate(self, run_id: str) -> dict:
        await self.store.update_run_status(run_id, RunStatus.AWAITING_HUMAN.value)
        critical_alarms = [a for a in self.alarm_manager.get_alarms() if a.severity.value == "CRITICAL"]
        return {
            "run_id": run_id,
            "status": RunStatus.AWAITING_HUMAN.value,
            "escalation": {
                "reason": critical_alarms[-1].recommended_action if critical_alarms else "Unknown",
                "alarm": critical_alarms[-1].model_dump() if critical_alarms else None,
            },
            "alarms": [a.model_dump() for a in self.alarm_manager.get_alarms()],
            "checkpoints": [c.model_dump() for c in self.checkpoint_manager.results],
        }

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract the first JSON object from agent text."""
        import re
        # Try to find JSON in code blocks first
        code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except json.JSONDecodeError:
                pass
        # Try to find bare JSON
        brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass
        return None
