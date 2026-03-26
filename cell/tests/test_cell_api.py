from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cell.api import Cell
from cell.types import CompletionStatus, TaskOutput


@pytest.mark.asyncio
async def test_stream_accepts_explicit_workflow_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_workflow_ids: list[str] = []

    async def fake_run(cls, instruction, **kwargs) -> TaskOutput:
        seen_workflow_ids.append(kwargs["workflow_id"])
        return TaskOutput(
            cell_id="cell-1",
            task_id=kwargs["workflow_id"],
            timestamp=datetime(2026, 3, 11, tzinfo=timezone.utc),
            result={"status": "ok"},
            result_schema_id="demo",
            confidence=0.9,
            completion_status=CompletionStatus.COMPLETE,
            sources=[],
            reasoning_summary="done",
            assumptions=[],
            tools_used=[],
            dynamic_tools_created=[],
            model_id="mock-model",
            blockers_encountered=0,
            retries=0,
            total_latency_ms=1,
            total_tokens={"input": 1, "output": 1},
            total_cost_usd=0.0,
            event_log_ref="event-log://cell-1/task-1",
            state_transitions=[],
            event_log=[],
            verifier_reports=[],
        )

    monkeypatch.setattr(Cell, "run", classmethod(fake_run))

    events = [event async for event in Cell.stream("extract data", workflow_id="wf-123")]

    assert seen_workflow_ids == ["wf-123"]
    assert events[0].event_type == "cell.started"
    assert events[-1].event_type == "cell.complete"
