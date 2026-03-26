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
    CompletionStatus,
    DiagnosisAction,
    MessageType,
    TaskInput,
    Topology,
)


def _render_context(task: TaskInput) -> str:
    return str(
        {
            "input_data": task.input_data,
            "input_documents": [document.model_dump(mode="json") for document in task.input_documents],
            "context": task.context,
            "result_schema_id": task.result_schema_id,
        }
    )


def _schema_matches(value: Any, schema: dict[str, Any]) -> bool:
    if not schema:
        return True
    schema_type = schema.get("type")
    if not schema_type:
        return True
    if schema_type == "object":
        if not isinstance(value, dict):
            return False
        required = schema.get("required", [])
        if any(name not in value for name in required):
            return False
        properties = schema.get("properties", {})
        for name, subschema in properties.items():
            if name in value and not _schema_matches(value[name], subschema):
                return False
        if schema.get("additionalProperties") is False:
            if any(name not in properties for name in value):
                return False
        return True
    if schema_type == "array":
        if not isinstance(value, list):
            return False
        item_schema = schema.get("items", {})
        return all(_schema_matches(item, item_schema) for item in value)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True


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
        actual_tools_used: set[str] = set()
        model_id = "deterministic"
        started_at = workflow.now()
        reasoning_summary = ""
        assumptions: list[str] = []
        sources: list[dict[str, Any]] = []
        result_payload: dict[str, Any] = {}
        completion_status = CompletionStatus.INCONCLUSIVE
        confidence = 0.0
        verifier_reports: list[dict[str, Any]] = []
        effective_budget = task.max_cost_usd if task.max_cost_usd is not None else cfg.cost.budget_usd

        def record_usage(result: dict[str, Any]) -> None:
            nonlocal total_cost_usd, total_latency_ms, model_id
            usage = result.get("token_usage", {})
            total_tokens["input"] += int(usage.get("input", 0))
            total_tokens["output"] += int(usage.get("output", 0))
            total_cost_usd += float(result.get("cost_usd", 0.0))
            total_latency_ms += int(result.get("latency_ms", 0))
            model_id = str(result.get("model_id", model_id))

        def record_verifier_report(result: dict[str, Any]) -> None:
            verifier_reports.append(
                {
                    "verdict_id": result.get("verdict_id", f"verifier-{len(verifier_reports) + 1}"),
                    "artifact_id": result["artifact_id"],
                    "spec_id": result["spec_id"],
                    "passed": result["passed"],
                    "results": result.get("results", []),
                    "failure_report": result.get("failure_report"),
                }
            )

        def timed_out() -> bool:
            return (workflow.now() - started_at).total_seconds() > cfg.limits.total_cell_timeout_sec

        def budget_exceeded() -> bool:
            return total_cost_usd > effective_budget

        def finish(final_state: CellState, summary: str) -> dict:
            nonlocal current_state
            if current_state != final_state:
                bus.log_state_transition(current_state, final_state)
                current_state = final_state
            output = build_output_envelope(
                cell_id=cfg.cell_id,
                task_id=task.task_id,
                result=result_payload or {"status": final_state.value},
                result_schema_id=task.result_schema_id,
                confidence=confidence,
                completion_status=completion_status,
                sources=sources,
                reasoning_summary=summary,
                assumptions=assumptions,
                tools_used=sorted(actual_tools_used),
                dynamic_tools_created=dynamic_tools,
                model_id=model_id,
                blockers_encountered=blockers_encountered,
                retries=retries,
                total_latency_ms=total_latency_ms,
                total_tokens=total_tokens,
                total_cost_usd=total_cost_usd,
                event_log=bus.get_log(),
                state_transitions=bus.get_state_transitions(),
                verifier_reports=verifier_reports,
                timestamp=workflow.now(),
            )
            return output.model_dump(mode="json")

        bus.log_state_transition(current_state, CellState.EXECUTING)
        current_state = CellState.EXECUTING

        while True:
            if timed_out():
                result_payload = {"status": "escalated", "reason": "Total cell timeout exceeded"}
                reasoning_summary = "Workflow exceeded the configured total cell timeout."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ESCALATED, reasoning_summary)

            executor_result = await workflow.execute_activity(
                "run_executor",
                args=[
                    task.model_dump(mode="json"),
                    tools,
                    {
                        **cfg.agent("executor").model_dump(mode="json"),
                        "sandbox_policy": cfg.sandbox.model_dump(mode="json"),
                    },
                    _render_context(task),
                ],
                start_to_close_timeout=timedelta(seconds=cfg.limits.execution_timeout_sec),
            )
            if timed_out():
                result_payload = {"status": "escalated", "reason": "Total cell timeout exceeded"}
                reasoning_summary = "Workflow exceeded the configured total cell timeout."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ESCALATED, reasoning_summary)
            record_usage(executor_result)
            bus.emit(
                CellMessage(
                    id=f"msg_exec_{len(bus.get_log())}",
                    timestamp=workflow.now(),
                    source_agent=AgentRole.EXECUTOR,
                    target_agent=AgentRole.RUNTIME,
                    message_type=MessageType.RESULT if executor_result["status"] == "complete" else MessageType.BLOCKER,
                    payload=executor_result["payload"],
                    correlation_id=f"exec-{blockers_encountered}",
                )
            )
            if budget_exceeded():
                result_payload = {"status": "escalated", "reason": "Budget exceeded"}
                reasoning_summary = "Workflow exceeded the configured budget after an agent call."
                completion_status = CompletionStatus.INCONCLUSIVE
                confidence = 0.0
                return finish(CellState.ESCALATED, reasoning_summary)

            if executor_result["status"] == "complete":
                payload = executor_result["payload"]
                actual_tools_used.update(payload.get("tools_invoked", []))
                candidate_result = payload.get("result", {})
                if not _schema_matches(candidate_result, task.result_schema):
                    result_payload = {
                        "status": "error",
                        "reason": "Executor result failed result_schema validation",
                    }
                    reasoning_summary = "Executor produced output that did not match the caller-defined result schema."
                    completion_status = CompletionStatus.INCONCLUSIVE
                    return finish(CellState.ERROR, reasoning_summary)
                result_payload = candidate_result
                confidence = float(payload.get("confidence", 0.0))
                sources = payload.get("sources", [])
                assumptions = payload.get("assumptions", [])
                completion_status = CompletionStatus(payload.get("completion_status", "complete"))
                reasoning_summary = "Executor completed the scoped task."
                return finish(CellState.COMPLETE, reasoning_summary)

            if executor_result["status"] == "error":
                result_payload = {"status": "error", "reason": executor_result["payload"]["error"]}
                reasoning_summary = "Executor returned an error."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ERROR, reasoning_summary)

            blockers_encountered += 1
            actual_tools_used.update(executor_result["payload"].get("tools_invoked", []))
            if blockers_encountered > cfg.limits.max_blockers_per_task:
                result_payload = {"status": "escalated", "reason": "Max blockers exceeded"}
                reasoning_summary = "Executor encountered too many blockers."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ESCALATED, reasoning_summary)
            if not task.allow_dynamic_tools:
                result_payload = {"status": "escalated", "reason": "Dynamic tools disabled for this task"}
                reasoning_summary = "Executor encountered a blocker but dynamic tool creation is disabled."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ESCALATED, reasoning_summary)

            planning_state = CellState.DIAGNOSING if cfg.topology == Topology.HIGH_TRUST else CellState.BUILDING
            bus.log_state_transition(current_state, planning_state)
            current_state = planning_state
            diagnosis = await workflow.execute_activity(
                "run_diagnostician",
                args=[executor_result["payload"]["blocker"], cfg.agent(cfg.planner_role()).model_dump(mode="json")],
                start_to_close_timeout=timedelta(seconds=cfg.limits.execution_timeout_sec),
            )
            if timed_out():
                result_payload = {"status": "escalated", "reason": "Total cell timeout exceeded"}
                reasoning_summary = "Workflow exceeded the configured total cell timeout."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ESCALATED, reasoning_summary)
            record_usage(diagnosis)
            if budget_exceeded():
                result_payload = {"status": "escalated", "reason": "Budget exceeded"}
                reasoning_summary = "Budget exceeded during blocker handling."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ESCALATED, reasoning_summary)

            action = diagnosis["payload"]["action"]
            if action == DiagnosisAction.ESCALATE.value:
                result_payload = {"status": "escalated", "reason": diagnosis["payload"]["escalation_reason"]}
                reasoning_summary = "The blocker was escalated."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ESCALATED, reasoning_summary)
            if action == DiagnosisAction.CONTEXT_REQUEST.value:
                if current_state != CellState.WAIT_HUMAN:
                    bus.log_state_transition(current_state, CellState.WAIT_HUMAN)
                    current_state = CellState.WAIT_HUMAN
                result_payload = {"status": "escalated", "reason": diagnosis["payload"]["context_needed"]}
                reasoning_summary = "Additional context is required to continue."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ESCALATED, reasoning_summary)
            if action == DiagnosisAction.USE_EXISTING.value:
                existing_tool_id = diagnosis["payload"]["existing_tool_id"]
                if existing_tool_id not in tools:
                    tools.append(existing_tool_id)
                bus.emit(
                    CellMessage(
                        id=f"msg_local_{len(bus.get_log())}",
                        timestamp=workflow.now(),
                        source_agent=AgentRole.RUNTIME,
                        target_agent=AgentRole.EXECUTOR,
                        message_type=MessageType.TOOL_READY,
                        payload={"tool_id": existing_tool_id, "source": "local_registry"},
                        correlation_id=f"tool-{blockers_encountered}",
                    )
                )
                bus.log_state_transition(current_state, CellState.EXECUTING)
                current_state = CellState.EXECUTING
                continue

            if action == DiagnosisAction.INSTALL_PUBLIC.value:
                public_tool_id = diagnosis["payload"]["public_tool_id"]
                if current_state != CellState.INSTALLING:
                    bus.log_state_transition(current_state, CellState.INSTALLING)
                    current_state = CellState.INSTALLING
                installed = await workflow.execute_activity(
                    "install_public_tool",
                    args=[public_tool_id, cfg.static_tools],
                    start_to_close_timeout=timedelta(seconds=cfg.limits.build_timeout_sec),
                )
                artifact = installed["artifact"]
                spec = installed["spec"]
                bus.log_state_transition(current_state, CellState.VERIFYING)
                current_state = CellState.VERIFYING
                verifier_result = await workflow.execute_activity(
                    "run_verifier",
                    args=[artifact, spec, cfg.sandbox.model_dump(mode="json")],
                    start_to_close_timeout=timedelta(seconds=cfg.limits.verify_timeout_sec),
                )
                record_verifier_report(verifier_result)
                if verifier_result["passed"]:
                    if artifact["name"] not in tools:
                        tools.append(artifact["name"])
                    dynamic_tools.append(artifact["name"])
                    bus.emit(
                        CellMessage(
                            id=f"msg_public_{len(bus.get_log())}",
                            timestamp=workflow.now(),
                            source_agent=AgentRole.RUNTIME,
                            target_agent=AgentRole.EXECUTOR,
                            message_type=MessageType.TOOL_READY,
                            payload={"tool_id": artifact["name"], "source": "public_library"},
                            correlation_id=f"tool-{blockers_encountered}",
                        )
                    )
                    bus.log_state_transition(current_state, CellState.EXECUTING)
                    current_state = CellState.EXECUTING
                    continue
                result_payload = {
                    "status": "escalated",
                    "reason": verifier_result.get("failure_report", "Installed public tool failed verification"),
                }
                reasoning_summary = "The public tool was installed but failed local verification."
                completion_status = CompletionStatus.INCONCLUSIVE
                return finish(CellState.ESCALATED, reasoning_summary)

            spec = diagnosis["payload"]["tool_spec"]
            previous_failure: dict[str, Any] | None = None
            build_attempts = 0
            if current_state != CellState.BUILDING:
                bus.log_state_transition(current_state, CellState.BUILDING)
                current_state = CellState.BUILDING
            while True:
                if timed_out():
                    result_payload = {"status": "escalated", "reason": "Total cell timeout exceeded"}
                    reasoning_summary = "Workflow timed out during tool building."
                    completion_status = CompletionStatus.INCONCLUSIVE
                    return finish(CellState.ESCALATED, reasoning_summary)

                builder_result = await workflow.execute_activity(
                    "run_builder",
                    args=[spec, cfg.agent(cfg.builder_role()).model_dump(mode="json"), previous_failure],
                    start_to_close_timeout=timedelta(seconds=cfg.limits.build_timeout_sec),
                )
                record_usage(builder_result)
                if budget_exceeded():
                    result_payload = {"status": "escalated", "reason": "Budget exceeded"}
                    reasoning_summary = "Budget exceeded during tool build."
                    completion_status = CompletionStatus.INCONCLUSIVE
                    return finish(CellState.ESCALATED, reasoning_summary)
                if builder_result["status"] != "complete":
                    result_payload = {"status": "error", "reason": builder_result["payload"].get("error", "build failed")}
                    reasoning_summary = "Builder returned an error."
                    completion_status = CompletionStatus.INCONCLUSIVE
                    return finish(CellState.ERROR, reasoning_summary)

                bus.log_state_transition(current_state, CellState.VERIFYING)
                current_state = CellState.VERIFYING
                artifact = builder_result["payload"]["artifact"]
                verifier_result = await workflow.execute_activity(
                    "run_verifier",
                    args=[artifact, spec, cfg.sandbox.model_dump(mode="json")],
                    start_to_close_timeout=timedelta(seconds=cfg.limits.verify_timeout_sec),
                )
                record_verifier_report(verifier_result)
                if verifier_result["passed"]:
                    registered = await workflow.execute_activity(
                        "register_dynamic_tool",
                        args=[artifact, spec, cfg.static_tools],
                        start_to_close_timeout=timedelta(seconds=cfg.limits.build_timeout_sec),
                    )
                    registered_tool_id = registered["tool_id"]
                    if registered_tool_id not in tools:
                        tools.append(registered_tool_id)
                    dynamic_tools.append(registered_tool_id)
                    bus.emit(
                        CellMessage(
                            id=f"msg_tool_{len(bus.get_log())}",
                            timestamp=workflow.now(),
                            source_agent=AgentRole.RUNTIME,
                            target_agent=AgentRole.EXECUTOR,
                            message_type=MessageType.TOOL_READY,
                            payload={"tool_id": registered_tool_id},
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
                    result_payload = {
                        "status": "escalated",
                        "reason": verifier_result.get("failure_report", "Tool verification failed"),
                    }
                    reasoning_summary = "Dynamic tool build exhausted retries."
                    completion_status = CompletionStatus.INCONCLUSIVE
                    return finish(CellState.ESCALATED, reasoning_summary)

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
