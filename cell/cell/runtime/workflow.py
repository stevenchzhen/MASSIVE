from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

from cell.config import CellConfig
from cell.output.envelope import build_output_envelope
from cell.runtime.bus import CellBus
from cell.types import (
    AgentRole,
    CellMessage,
    CellState,
    MessageType,
    TaskInput,
    VerdictType,
)


@workflow.defn(name="CellWorkflow")
class CellWorkflow:
    @workflow.run
    async def run(self, task_input: dict, config: dict) -> dict:
        cfg = CellConfig.model_validate(config)
        task = TaskInput.model_validate(task_input)
        bus = CellBus(cfg.cell_id, task.task_id, now_fn=workflow.now)

        current_state = CellState.INITIALIZING
        total_tokens = {"input": 0, "output": 0}
        total_cost_usd = 0.0
        total_latency_ms = 0
        blockers_encountered = 0
        retries = 0
        dynamic_tools: list[str] = []
        tools = list(cfg.static_tools)
        model_id = "deterministic"
        started_at = workflow.now()
        last_reasoning_summary = ""
        assumptions: list[str] = []
        evidence: list[dict[str, Any]] = []
        verdict: dict[str, Any] = {}
        verdict_type = VerdictType.INCONCLUSIVE
        confidence = 0.0

        def record_usage(result: dict[str, Any]) -> None:
            nonlocal total_cost_usd, total_latency_ms, model_id
            usage = result.get("token_usage", {})
            total_tokens["input"] += int(usage.get("input", 0))
            total_tokens["output"] += int(usage.get("output", 0))
            total_cost_usd += float(result.get("cost_usd", 0.0))
            total_latency_ms += int(result.get("latency_ms", 0))
            model_id = str(result.get("model_id", model_id))

        def timed_out() -> bool:
            return (workflow.now() - started_at).total_seconds() > cfg.limits.total_cell_timeout_sec

        def budget_exceeded() -> bool:
            return total_cost_usd > cfg.cost.budget_usd

        def finish(final_state: CellState, summary: str) -> dict:
            nonlocal current_state
            if current_state != final_state:
                bus.log_state_transition(current_state, final_state)
                current_state = final_state
            envelope = build_output_envelope(
                cell_id=cfg.cell_id,
                task_id=task.task_id,
                verdict=verdict or {"status": final_state.value},
                confidence=confidence,
                verdict_type=verdict_type,
                evidence=evidence,
                reasoning_summary=summary,
                assumptions=assumptions,
                tools_used=tools,
                dynamic_tools_created=dynamic_tools,
                model_id=model_id,
                blockers_encountered=blockers_encountered,
                retries=retries,
                total_latency_ms=total_latency_ms,
                total_tokens=total_tokens,
                total_cost_usd=total_cost_usd,
                event_log=bus.get_log(),
                state_transitions=bus.get_state_transitions(),
                timestamp=workflow.now(),
            )
            return envelope.model_dump(mode="json")

        bus.log_state_transition(current_state, CellState.EXECUTING)
        current_state = CellState.EXECUTING

        while True:
            if timed_out():
                verdict = {"status": "escalated", "reason": "Total cell timeout exceeded"}
                last_reasoning_summary = "Workflow exceeded the configured total cell timeout."
                return finish(CellState.ESCALATED, last_reasoning_summary)

            executor_result = await workflow.execute_activity(
                "run_executor",
                args=[task.model_dump(mode="json"), tools, cfg.models.executor, task.context],
                start_to_close_timeout=timedelta(seconds=cfg.limits.execution_timeout_sec),
            )
            if timed_out():
                verdict = {"status": "escalated", "reason": "Total cell timeout exceeded"}
                last_reasoning_summary = "Workflow exceeded the configured total cell timeout."
                return finish(CellState.ESCALATED, last_reasoning_summary)
            record_usage(executor_result)
            bus.emit(
                CellMessage(
                    id=f"msg_exec_{len(bus.get_log())}",
                    timestamp=workflow.now(),
                    source_agent=AgentRole.EXECUTOR,
                    target_agent=AgentRole.RUNTIME,
                    message_type=MessageType.VERDICT
                    if executor_result["status"] == "complete"
                    else MessageType.BLOCKER,
                    payload=executor_result["payload"],
                    correlation_id=f"exec-{blockers_encountered}",
                )
            )
            if budget_exceeded():
                verdict = {"status": "escalated", "reason": "Budget exceeded"}
                last_reasoning_summary = "Workflow exceeded the configured budget after an agent call."
                verdict_type = VerdictType.INCONCLUSIVE
                confidence = 0.0
                return finish(CellState.ESCALATED, last_reasoning_summary)

            if executor_result["status"] == "complete":
                payload = executor_result["payload"]
                verdict = payload.get("findings", {})
                confidence = float(payload.get("confidence", 0.0))
                evidence = payload.get("evidence", [])
                assumptions = payload.get("assumptions", [])
                verdict_type = (
                    VerdictType.CONCLUSIVE if confidence >= 0.85 else VerdictType.QUALIFIED
                )
                last_reasoning_summary = "Executor completed the scoped task."
                return finish(CellState.COMPLETE, last_reasoning_summary)

            if executor_result["status"] == "error":
                verdict = {"status": "error", "reason": executor_result["payload"]["error"]}
                last_reasoning_summary = "Executor returned an error."
                return finish(CellState.ERROR, last_reasoning_summary)

            blockers_encountered += 1
            if blockers_encountered > cfg.limits.max_blockers_per_task:
                verdict = {"status": "escalated", "reason": "Max blockers exceeded"}
                last_reasoning_summary = "Executor encountered too many blockers."
                return finish(CellState.ESCALATED, last_reasoning_summary)

            bus.log_state_transition(current_state, CellState.DIAGNOSING)
            current_state = CellState.DIAGNOSING
            diagnosis = await workflow.execute_activity(
                "run_diagnostician",
                args=[executor_result["payload"]["blocker"], cfg.models.diagnostician],
                start_to_close_timeout=timedelta(seconds=cfg.limits.execution_timeout_sec),
            )
            if timed_out():
                verdict = {"status": "escalated", "reason": "Total cell timeout exceeded"}
                last_reasoning_summary = "Workflow exceeded the configured total cell timeout."
                return finish(CellState.ESCALATED, last_reasoning_summary)
            record_usage(diagnosis)
            if budget_exceeded():
                verdict = {"status": "escalated", "reason": "Budget exceeded"}
                last_reasoning_summary = "Budget exceeded during blocker diagnosis."
                return finish(CellState.ESCALATED, last_reasoning_summary)

            action = diagnosis["payload"]["action"]
            if action == "escalate":
                verdict = {"status": "escalated", "reason": diagnosis["payload"]["escalation_reason"]}
                last_reasoning_summary = "Diagnostician escalated the blocker."
                return finish(CellState.ESCALATED, last_reasoning_summary)
            if action == "context_request":
                bus.log_state_transition(current_state, CellState.WAIT_HUMAN)
                current_state = CellState.WAIT_HUMAN
                verdict = {"status": "escalated", "reason": diagnosis["payload"]["context_needed"]}
                last_reasoning_summary = "Diagnostician requested additional context unavailable inside the cell."
                return finish(CellState.ESCALATED, last_reasoning_summary)

            spec = diagnosis["payload"]["tool_spec"]
            previous_failure: dict[str, Any] | None = None
            build_attempts = 0
            bus.log_state_transition(current_state, CellState.BUILDING)
            current_state = CellState.BUILDING
            while True:
                if timed_out():
                    verdict = {"status": "escalated", "reason": "Total cell timeout exceeded"}
                    last_reasoning_summary = "Workflow timed out during tool building."
                    return finish(CellState.ESCALATED, last_reasoning_summary)

                builder_result = await workflow.execute_activity(
                    "run_builder",
                    args=[spec, cfg.models.builder, previous_failure],
                    start_to_close_timeout=timedelta(seconds=cfg.limits.build_timeout_sec),
                )
                record_usage(builder_result)
                if budget_exceeded():
                    verdict = {"status": "escalated", "reason": "Budget exceeded"}
                    last_reasoning_summary = "Budget exceeded during tool build."
                    return finish(CellState.ESCALATED, last_reasoning_summary)
                if builder_result["status"] != "complete":
                    verdict = {"status": "error", "reason": builder_result["payload"].get("error", "build failed")}
                    last_reasoning_summary = "Builder returned an error."
                    return finish(CellState.ERROR, last_reasoning_summary)

                bus.log_state_transition(current_state, CellState.VERIFYING)
                current_state = CellState.VERIFYING
                artifact = builder_result["payload"]["artifact"]
                verifier_result = await workflow.execute_activity(
                    "run_verifier",
                    args=[artifact, spec, cfg.sandbox.model_dump(mode="json")],
                    start_to_close_timeout=timedelta(seconds=cfg.limits.verify_timeout_sec),
                )
                if verifier_result["passed"]:
                    tools.append(artifact["name"])
                    dynamic_tools.append(artifact["name"])
                    bus.emit(
                        CellMessage(
                            id=f"msg_tool_{len(bus.get_log())}",
                            timestamp=workflow.now(),
                            source_agent=AgentRole.RUNTIME,
                            target_agent=AgentRole.EXECUTOR,
                            message_type=MessageType.TOOL_READY,
                            payload={"tool_id": artifact["name"]},
                            correlation_id=f"tool-{blockers_encountered}",
                        )
                    )
                    bus.log_state_transition(current_state, CellState.EXECUTING)
                    current_state = CellState.EXECUTING
                    break

                build_attempts += 1
                retries += 1
                previous_failure = {
                    "source_code": artifact["source_code"],
                    "failure_report": verifier_result.get("failure_report"),
                }
                if build_attempts >= cfg.limits.max_tool_build_retries:
                    bus.log_state_transition(current_state, CellState.TOOL_FAILED)
                    current_state = CellState.TOOL_FAILED
                    verdict = {
                        "status": "escalated",
                        "reason": verifier_result.get("failure_report", "Tool verification failed"),
                    }
                    last_reasoning_summary = "Dynamic tool build exhausted retries."
                    return finish(CellState.ESCALATED, last_reasoning_summary)

                bus.emit(
                    CellMessage(
                        id=f"msg_retry_{len(bus.get_log())}",
                        timestamp=workflow.now(),
                        source_agent=AgentRole.RUNTIME,
                        target_agent=AgentRole.BUILDER,
                        message_type=MessageType.TOOL_BUILD_RETRY,
                        payload=previous_failure,
                        correlation_id=f"tool-{blockers_encountered}",
                    )
                )
                bus.log_state_transition(current_state, CellState.BUILDING)
                current_state = CellState.BUILDING
