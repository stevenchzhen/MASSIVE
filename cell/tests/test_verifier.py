from cell.agents.verifier import VerifierAgent
from cell.tools.sandbox import Sandbox, SandboxPolicy
from cell.types import TestCase, ToolArtifact, ToolSpec


def _policy(timeout: int = 2) -> SandboxPolicy:
    return SandboxPolicy(
        max_execution_time_sec=timeout,
        max_memory_mb=128,
        allowed_imports=["math", "statistics"],
    )


def _spec() -> ToolSpec:
    return ToolSpec(
        name="adder",
        description="Adds two numbers",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "number"}},
            "required": ["result"],
            "additionalProperties": False,
        },
        test_cases=[
            TestCase(description="positive", input={"a": 1, "b": 2}, expected_output={"result": 3}),
            TestCase(description="negative", input={"a": -1, "b": 2}, expected_output={"result": 1}),
            TestCase(description="zero", input={"a": 0, "b": 0}, expected_output={"result": 0}),
        ],
        edge_cases=[
            TestCase(description="float", input={"a": 1.5, "b": 2.5}, expected_output={"result": 4.0}),
            TestCase(description="large", input={"a": 10000, "b": 1}, expected_output={"result": 10001}),
        ],
        constraints=["pure"],
    )


async def test_verifier_fails_disallowed_import() -> None:
    agent = VerifierAgent()
    artifact = ToolArtifact(
        spec_id="spec-1",
        name="adder",
        entry_point="adder",
        source_code="import os\ndef adder(a, b):\n    return {'result': a + b}\n",
    )
    verdict = await agent.verify(artifact, _spec(), Sandbox(_policy()))
    assert verdict.passed is False
    assert "Disallowed imports" in verdict.failure_report


async def test_verifier_fails_open_call() -> None:
    agent = VerifierAgent()
    artifact = ToolArtifact(
        spec_id="spec-1",
        name="adder",
        entry_point="adder",
        source_code="def adder(a, b):\n    open('x')\n    return {'result': a + b}\n",
    )
    verdict = await agent.verify(artifact, _spec(), Sandbox(_policy()))
    assert verdict.passed is False
    assert "Forbidden usage detected" in verdict.failure_report


async def test_verifier_passes_valid_tool() -> None:
    agent = VerifierAgent()
    artifact = ToolArtifact(
        spec_id="spec-1",
        name="adder",
        entry_point="adder",
        source_code="def adder(a, b):\n    return {'result': a + b}\n",
    )
    verdict = await agent.verify(artifact, _spec(), Sandbox(_policy()))
    assert verdict.passed is True


async def test_verifier_fails_on_wrong_output() -> None:
    agent = VerifierAgent()
    artifact = ToolArtifact(
        spec_id="spec-1",
        name="adder",
        entry_point="adder",
        source_code="def adder(a, b):\n    return {'result': a - b}\n",
    )
    verdict = await agent.verify(artifact, _spec(), Sandbox(_policy()))
    assert verdict.passed is False
    assert "Unexpected output" in verdict.failure_report


async def test_verifier_reports_timeout() -> None:
    agent = VerifierAgent()
    artifact = ToolArtifact(
        spec_id="spec-1",
        name="adder",
        entry_point="adder",
        source_code="def adder(a, b):\n    while True:\n        pass\n",
    )
    verdict = await agent.verify(artifact, _spec(), Sandbox(_policy(timeout=1)))
    assert verdict.passed is False
    assert "TimeoutError" in verdict.failure_report or "exceeded" in verdict.failure_report


async def test_verifier_reports_crash() -> None:
    agent = VerifierAgent()
    artifact = ToolArtifact(
        spec_id="spec-1",
        name="adder",
        entry_point="adder",
        source_code="def adder(a, b):\n    raise ValueError('boom')\n",
    )
    verdict = await agent.verify(artifact, _spec(), Sandbox(_policy()))
    assert verdict.passed is False
    assert "Execution error" in verdict.failure_report


async def test_fuzz_inputs_do_not_crash_valid_tool() -> None:
    agent = VerifierAgent()
    artifact = ToolArtifact(
        spec_id="spec-1",
        name="adder",
        entry_point="adder",
        source_code="def adder(a=0, b=0):\n    return {'result': (a or 0) + (b or 0)}\n",
    )
    verdict = await agent.verify(artifact, _spec(), Sandbox(_policy()))
    fuzz_results = [result for result in verdict.results if result.check_name == "fuzz"]
    assert fuzz_results
    assert all(result.passed for result in fuzz_results)


async def test_verifier_runs_regression_cases_for_adapted_tool() -> None:
    agent = VerifierAgent()
    spec = _spec().model_copy(
        update={
            "base_tool_id": "adder_v1",
            "base_test_cases": [
                TestCase(description="regression", input={"a": 2, "b": 2}, expected_output={"result": 4})
            ],
        }
    )
    artifact = ToolArtifact(
        spec_id=spec.spec_id,
        name="adder_v2",
        entry_point="adder",
        source_code="def adder(a, b):\n    return {'result': a + b}\n",
    )
    verdict = await agent.verify(artifact, spec, Sandbox(_policy()))
    regression_results = [result for result in verdict.results if result.check_name.startswith("regression:")]
    assert regression_results
    assert all(result.passed for result in regression_results)


async def test_verifier_runs_task_validation_cases() -> None:
    agent = VerifierAgent()
    spec = _spec().model_copy(
        update={
            "task_validation_cases": [
                TestCase(description="task-derived", input={"a": 3, "b": 4}, expected_output={"result": 7})
            ]
        }
    )
    artifact = ToolArtifact(
        spec_id=spec.spec_id,
        name="adder",
        entry_point="adder",
        source_code="def adder(a, b):\n    return {'result': a + b}\n",
    )
    verdict = await agent.verify(artifact, spec, Sandbox(_policy()))
    task_results = [result for result in verdict.results if result.check_name.startswith("task-data:")]
    assert task_results
    assert all(result.passed for result in task_results)
