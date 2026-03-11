from datetime import datetime, timezone
from pathlib import Path

from cell.config import CellConfig, load_cell_config
from cell.types import (
    Blocker,
    BlockerCategory,
    CellMessage,
    CellOutputEnvelope,
    EvidenceItem,
    MessageType,
    TaskInput,
    ToolSpec,
    TestCase,
    VerdictType,
)


def test_task_input_round_trip() -> None:
    task = TaskInput(task_id="task-1", scope="analyze data", context="ctx")
    assert TaskInput.model_validate_json(task.model_dump_json()) == task


def test_blocker_round_trip() -> None:
    blocker = Blocker(
        category=BlockerCategory.MISSING_CAPABILITY,
        description="Need a parser",
        attempted_approaches=["manual parsing"],
        what_would_unblock="Create parser tool",
        input_sample='{"x": 1}',
        confidence_in_diagnosis=0.9,
    )
    assert Blocker.model_validate_json(blocker.model_dump_json()) == blocker


def test_tool_spec_requires_minimum_cases() -> None:
    cases = [TestCase(description=f"case-{i}", input={"x": i}, expected_output=i) for i in range(3)]
    edges = [TestCase(description=f"edge-{i}", input={"x": i}, expected_output=i) for i in range(2)]
    spec = ToolSpec(
        name="tool",
        description="desc",
        input_schema={"type": "object"},
        output_schema={"type": "number"},
        test_cases=cases,
        edge_cases=edges,
        constraints=["pure"],
    )
    assert spec.name == "tool"


def test_output_envelope_round_trip() -> None:
    envelope = CellOutputEnvelope(
        cell_id="cell-1",
        task_id="task-1",
        timestamp=datetime(2026, 3, 10, tzinfo=timezone.utc),
        verdict={"answer": 42},
        confidence=0.8,
        verdict_type=VerdictType.CONCLUSIVE,
        evidence=[
            EvidenceItem(
                summary="calc",
                content={"value": 42},
                source="tool",
                confidence=0.9,
            )
        ],
        reasoning_summary="Summarized reasoning",
        assumptions=["input is correct"],
        tools_used=["calculator_basic"],
        dynamic_tools_created=[],
        model_id="mock-model",
        blockers_encountered=0,
        retries=0,
        total_latency_ms=10,
        total_tokens={"input": 1, "output": 2},
        total_cost_usd=0.01,
        event_log_ref="event-log://cell-1/task-1",
        state_transitions=["executing", "complete"],
    )
    dumped = envelope.model_dump_json()
    assert CellOutputEnvelope.model_validate_json(dumped).verdict["answer"] == 42


def test_cell_message_round_trip() -> None:
    message = CellMessage(
        source_agent="executor",
        target_agent="runtime",
        message_type=MessageType.VERDICT,
        payload={"status": "complete"},
        correlation_id="corr-1",
    )
    assert CellMessage.model_validate_json(message.model_dump_json()) == message


def test_default_config_loads() -> None:
    path = Path(__file__).resolve().parents[1] / "configs" / "default_cell.yaml"
    config = load_cell_config(path)
    assert isinstance(config, CellConfig)
    assert config.models.executor == "claude-sonnet-4-20250514"
