from datetime import datetime, timezone

import pytest

from cell.runtime.bus import CellBus
from cell.types import AgentRole, CellMessage, CellState, MessageType


def test_emit_logs_message_summary() -> None:
    bus = CellBus("cell-1", "task-1", now_fn=lambda: datetime(2026, 3, 10, tzinfo=timezone.utc))
    bus.emit(
        CellMessage(
            source_agent=AgentRole.EXECUTOR,
            target_agent=AgentRole.RUNTIME,
            message_type=MessageType.RESULT,
            payload={"status": "complete", "sources": [{"a": 1}]},
            correlation_id="corr-1",
        )
    )
    log = bus.get_log()
    assert len(log) == 1
    assert log[0].payload_summary["status"] == "complete"
    assert log[0].payload_summary["sources"] == [{"a": 1}]


def test_state_transition_logged() -> None:
    bus = CellBus("cell-1", "task-1", now_fn=lambda: datetime(2026, 3, 10, tzinfo=timezone.utc))
    bus.log_state_transition(CellState.INITIALIZING, CellState.EXECUTING)
    assert bus.get_state_transitions() == ["executing"]


def test_invalid_transition_rejected() -> None:
    bus = CellBus("cell-1", "task-1")
    with pytest.raises(ValueError):
        bus.log_state_transition(CellState.INITIALIZING, CellState.COMPLETE)
