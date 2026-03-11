from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from cell.runtime.state import ensure_transition
from cell.types import AgentRole, CellMessage, CellState, EventLogEntry


class CellBus:
    def __init__(
        self,
        cell_id: str,
        task_id: str,
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.cell_id = cell_id
        self.task_id = task_id
        self._log: list[EventLogEntry] = []
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def emit(self, message: CellMessage) -> None:
        self._log.append(
            EventLogEntry(
                timestamp=message.timestamp,
                cell_id=self.cell_id,
                task_id=self.task_id,
                event="message",
                agent=message.source_agent,
                message_type=message.message_type,
                payload_summary=self._summarize(message.payload),
                correlation_id=message.correlation_id,
            )
        )

    def log_state_transition(self, from_state: CellState, to_state: CellState) -> None:
        ensure_transition(from_state, to_state)
        self._log.append(
            EventLogEntry(
                timestamp=self._now_fn(),
                cell_id=self.cell_id,
                task_id=self.task_id,
                event="state_transition",
                agent=AgentRole.RUNTIME,
                payload_summary={"from": from_state.value, "to": to_state.value},
                state=to_state,
            )
        )

    def get_log(self) -> list[EventLogEntry]:
        return list(self._log)

    def get_state_transitions(self) -> list[str]:
        return [entry.state.value for entry in self._log if entry.event == "state_transition" and entry.state]

    def _summarize(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                summary[key] = value
            elif isinstance(value, list):
                summary[key] = f"list[{len(value)}]"
            elif isinstance(value, dict):
                summary[key] = f"dict[{','.join(sorted(value.keys())[:5])}]"
            else:
                summary[key] = type(value).__name__
        return summary

