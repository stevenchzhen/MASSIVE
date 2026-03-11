from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import timedelta

import pytest

temporalio = pytest.importorskip("temporalio")
from temporalio import activity  # type: ignore[assignment]
from temporalio.client import Client  # type: ignore[assignment]
from temporalio.testing import WorkflowEnvironment  # type: ignore[assignment]
from temporalio.worker import Worker  # type: ignore[assignment]

from cell.runtime.workflow import CellWorkflow


def _base_config() -> dict:
    return {
        "cell_id": "cell_default",
        "version": "1.0.0",
        "models": {
            "executor": "claude-sonnet-4-20250514",
            "diagnostician": "claude-sonnet-4-20250514",
            "builder": "claude-sonnet-4-20250514",
            "verifier": None,
        },
        "limits": {
            "max_execution_retries": 3,
            "max_tool_build_retries": 2,
            "max_blockers_per_task": 5,
            "execution_timeout_sec": 10,
            "build_timeout_sec": 10,
            "verify_timeout_sec": 10,
            "total_cell_timeout_sec": 30,
        },
        "static_tools": ["calculator_basic"],
        "sandbox": {
            "max_execution_time_sec": 2,
            "max_memory_mb": 128,
            "allowed_imports": ["math"],
        },
        "cost": {"budget_usd": 5.0, "alert_threshold_usd": 3.0},
    }


def _task() -> dict:
    return {"task_id": "task-1", "scope": "analyze", "context": "ctx", "metadata": {}}


async def _execute_with_activities(executor_fn, diagnostician_fn, builder_fn, verifier_fn, config: dict) -> dict:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        client: Client = env.client
        async with Worker(
            client,
            task_queue="test-cell",
            workflows=[CellWorkflow],
            activities=[executor_fn, diagnostician_fn, builder_fn, verifier_fn],
        ):
            return await client.execute_workflow(
                "CellWorkflow",
                args=[_task(), config],
                id="workflow-test",
                task_queue="test-cell",
                execution_timeout=timedelta(seconds=60),
            )


@activity.defn(name="run_builder")
async def _unused_builder(spec: dict, model_config: dict | str, previous_failure: dict | None = None) -> dict:
    return {"status": "error", "payload": {"error": "unused"}, "token_usage": {"input": 0, "output": 0}, "model_id": "mock", "latency_ms": 0, "cost_usd": 0.0}


@activity.defn(name="run_verifier")
async def _unused_verifier(artifact: dict, spec: dict, sandbox_config: dict) -> dict:
    return {"passed": True, "results": [], "failure_report": None, "artifact_id": "a", "spec_id": "s"}


@pytest.mark.timeout(30)
async def test_workflow_happy_path() -> None:
    @activity.defn(name="run_executor")
    async def run_executor(task_input: dict, tools: list[str], model_config: dict | str, context: str) -> dict:
        return {
            "status": "complete",
            "payload": {
                "confidence": 0.9,
                "findings": {"answer": 42},
                "evidence": [{"summary": "calc"}],
                "assumptions": [],
            },
            "token_usage": {"input": 1, "output": 1},
            "model_id": "mock",
            "latency_ms": 5,
            "cost_usd": 0.01,
        }

    @activity.defn(name="run_diagnostician")
    async def run_diagnostician(blocker: dict, model_config: dict | str) -> dict:
        return {}

    result = await _execute_with_activities(run_executor, run_diagnostician, _unused_builder, _unused_verifier, _base_config())
    assert result["state_transitions"] == ["executing", "complete"]
    assert result["verdict"] == {"answer": 42}


@pytest.mark.timeout(30)
async def test_workflow_blocker_triggers_tool_build_loop() -> None:
    state = {"count": 0}

    @activity.defn(name="run_executor")
    async def run_executor(task_input: dict, tools: list[str], model_config: dict | str, context: str) -> dict:
        if state["count"] == 0:
            state["count"] += 1
            return {
                "status": "blocker",
                "payload": {
                    "blocker": {
                        "blocker_id": "blk-1",
                        "category": "missing_capability",
                        "description": "Need adder",
                        "attempted_approaches": ["manual"],
                        "what_would_unblock": "Build adder",
                        "input_sample": None,
                        "confidence_in_diagnosis": 0.9,
                    }
                },
                "token_usage": {"input": 1, "output": 1},
                "model_id": "mock",
                "latency_ms": 5,
                "cost_usd": 0.01,
            }
        return {
            "status": "complete",
            "payload": {
                "confidence": 0.88,
                "findings": {"answer": "done"},
                "evidence": [{"summary": "tool ready"}],
                "assumptions": [],
            },
            "token_usage": {"input": 1, "output": 1},
            "model_id": "mock",
            "latency_ms": 5,
            "cost_usd": 0.01,
        }

    @activity.defn(name="run_diagnostician")
    async def run_diagnostician(blocker: dict, model_config: dict | str) -> dict:
        return {
            "status": "complete",
            "payload": {
                "action": "tool_spec",
                "tool_spec": {
                    "spec_id": "spec-1",
                    "name": "adder",
                    "description": "Adds two numbers",
                    "input_schema": {
                        "type": "object",
                        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                        "required": ["a", "b"],
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {"result": {"type": "number"}},
                        "required": ["result"],
                    },
                    "test_cases": [
                        {"description": "one", "input": {"a": 1, "b": 2}, "expected_output": {"result": 3}},
                        {"description": "two", "input": {"a": 2, "b": 3}, "expected_output": {"result": 5}},
                        {"description": "three", "input": {"a": 0, "b": 0}, "expected_output": {"result": 0}},
                    ],
                    "edge_cases": [
                        {"description": "large", "input": {"a": 10000, "b": 1}, "expected_output": {"result": 10001}},
                        {"description": "float", "input": {"a": 1.5, "b": 2.5}, "expected_output": {"result": 4.0}},
                    ],
                    "constraints": ["pure"],
                },
            },
            "token_usage": {"input": 1, "output": 1},
            "model_id": "mock",
            "latency_ms": 5,
            "cost_usd": 0.01,
        }

    @activity.defn(name="run_builder")
    async def run_builder(spec: dict, model_config: dict | str, previous_failure: dict | None = None) -> dict:
        return {
            "status": "complete",
            "payload": {
                "artifact": {
                    "artifact_id": "art-1",
                    "spec_id": "spec-1",
                    "name": "adder",
                    "entry_point": "adder",
                    "source_code": "def adder(a,b): return {'result': a+b}",
                    "created_at": "2026-03-10T00:00:00Z",
                }
            },
            "token_usage": {"input": 1, "output": 1},
            "model_id": "mock",
            "latency_ms": 5,
            "cost_usd": 0.01,
        }

    @activity.defn(name="run_verifier")
    async def run_verifier(artifact: dict, spec: dict, sandbox_config: dict) -> dict:
        return {"artifact_id": "art-1", "spec_id": "spec-1", "passed": True, "results": [], "failure_report": None}

    result = await _execute_with_activities(run_executor, run_diagnostician, run_builder, run_verifier, _base_config())
    assert result["state_transitions"] == ["executing", "diagnosing", "building", "verifying", "executing", "complete"]
    assert "adder" in result["dynamic_tools_created"]


@pytest.mark.timeout(30)
async def test_workflow_max_blockers_escalates() -> None:
    @activity.defn(name="run_executor")
    async def run_executor(task_input: dict, tools: list[str], model_config: dict | str, context: str) -> dict:
        return {
            "status": "blocker",
            "payload": {
                "blocker": {
                    "blocker_id": "blk-1",
                    "category": "missing_capability",
                    "description": "Need tool",
                    "attempted_approaches": ["manual"],
                    "what_would_unblock": "Build tool",
                    "input_sample": None,
                    "confidence_in_diagnosis": 0.9,
                }
            },
            "token_usage": {"input": 1, "output": 1},
            "model_id": "mock",
            "latency_ms": 5,
            "cost_usd": 0.01,
        }

    @activity.defn(name="run_diagnostician")
    async def run_diagnostician(blocker: dict, model_config: dict | str) -> dict:
        return {
            "status": "complete",
            "payload": {"action": "escalate", "escalation_reason": "Cannot resolve"},
            "token_usage": {"input": 1, "output": 1},
            "model_id": "mock",
            "latency_ms": 5,
            "cost_usd": 0.01,
        }

    config = _base_config()
    config["limits"]["max_blockers_per_task"] = 0
    result = await _execute_with_activities(run_executor, run_diagnostician, _unused_builder, _unused_verifier, config)
    assert result["state_transitions"] == ["executing", "escalated"]
    assert result["verdict"]["reason"] == "Max blockers exceeded"


@pytest.mark.timeout(30)
async def test_workflow_budget_exceeded_triggers_graceful_termination() -> None:
    @activity.defn(name="run_executor")
    async def run_executor(task_input: dict, tools: list[str], model_config: dict | str, context: str) -> dict:
        return {
            "status": "complete",
            "payload": {"confidence": 0.9, "findings": {"answer": 1}, "evidence": [], "assumptions": []},
            "token_usage": {"input": 1, "output": 1},
            "model_id": "mock",
            "latency_ms": 5,
            "cost_usd": 10.0,
        }

    @activity.defn(name="run_diagnostician")
    async def run_diagnostician(blocker: dict, model_config: dict | str) -> dict:
        return {}

    config = _base_config()
    config["cost"]["budget_usd"] = 0.5
    result = await _execute_with_activities(run_executor, run_diagnostician, _unused_builder, _unused_verifier, config)
    assert result["state_transitions"] == ["executing", "escalated"]
    assert result["verdict"]["reason"] == "Budget exceeded"


@pytest.mark.timeout(30)
async def test_workflow_timeout_triggers_escalation() -> None:
    @activity.defn(name="run_executor")
    async def run_executor(task_input: dict, tools: list[str], model_config: dict | str, context: str) -> dict:
        await asyncio.sleep(2)
        return {
            "status": "complete",
            "payload": {"confidence": 0.9, "findings": {"answer": 1}, "evidence": [], "assumptions": []},
            "token_usage": {"input": 1, "output": 1},
            "model_id": "mock",
            "latency_ms": 5,
            "cost_usd": 0.01,
        }

    @activity.defn(name="run_diagnostician")
    async def run_diagnostician(blocker: dict, model_config: dict | str) -> dict:
        return {}

    config = _base_config()
    config["limits"]["total_cell_timeout_sec"] = 1
    result = await _execute_with_activities(run_executor, run_diagnostician, _unused_builder, _unused_verifier, config)
    assert result["state_transitions"] == ["executing", "escalated"]
    assert result["verdict"]["reason"] == "Total cell timeout exceeded"
