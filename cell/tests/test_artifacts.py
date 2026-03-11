from datetime import datetime, timezone

from cell.artifacts import load_artifact_bundle, write_artifact_bundle
from cell.types import (
    AgentRole,
    Blocker,
    BlockerCategory,
    CompletionStatus,
    EventLogEntry,
    MessageType,
    TaskInput,
    TaskOutput,
)


def test_artifact_bundle_round_trip(tmp_path) -> None:
    task_input = TaskInput(
        task_id="task-1",
        instruction="extract fields",
        input_data={"mode": "demo"},
        result_schema={"type": "object"},
    )
    blocker = Blocker(
        blocker_id="blk-1",
        category=BlockerCategory.MISSING_CAPABILITY,
        description="Need a parser",
        attempted_approaches=["manual parsing"],
        what_would_unblock="Create parser tool",
        input_sample="sample",
        confidence_in_diagnosis=0.9,
    )
    task_output = TaskOutput(
        cell_id="cell-1",
        task_id="task-1",
        timestamp=datetime(2026, 3, 10, tzinfo=timezone.utc),
        result={"answer": 42},
        result_schema_id="demo",
        confidence=0.8,
        completion_status=CompletionStatus.COMPLETE,
        sources=[],
        reasoning_summary="done",
        assumptions=[],
        tools_used=["csv_reader"],
        dynamic_tools_created=["invoice_parser"],
        model_id="mock-model",
        blockers_encountered=1,
        retries=0,
        total_latency_ms=5,
        total_tokens={"input": 1, "output": 1},
        total_cost_usd=0.01,
        event_log_ref="event-log://cell-1/task-1",
        state_transitions=["executing", "diagnosing", "complete"],
        event_log=[
            EventLogEntry(
                timestamp=datetime(2026, 3, 10, tzinfo=timezone.utc),
                cell_id="cell-1",
                task_id="task-1",
                event="message",
                agent=AgentRole.EXECUTOR,
                message_type=MessageType.BLOCKER,
                payload_summary={"blocker": blocker.model_dump(mode="json")},
                correlation_id="corr-1",
            )
        ],
        verifier_reports=[],
    )

    write_artifact_bundle(tmp_path, task_input, task_output)
    bundle = load_artifact_bundle(tmp_path)

    assert bundle.input_manifest.task_id == "task-1"
    assert bundle.blockers[0].description == "Need a parser"
    assert bundle.task_output.result["answer"] == 42
