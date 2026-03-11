from __future__ import annotations

from cell.types import CellState


VALID_TRANSITIONS: dict[CellState, set[CellState]] = {
    CellState.INITIALIZING: {CellState.EXECUTING, CellState.ERROR},
    CellState.EXECUTING: {
        CellState.COMPLETE,
        CellState.DIAGNOSING,
        CellState.BUILDING,
        CellState.INSTALLING,
        CellState.ERROR,
        CellState.ESCALATED,
    },
    CellState.DIAGNOSING: {
        CellState.EXECUTING,
        CellState.INSTALLING,
        CellState.BUILDING,
        CellState.WAIT_HUMAN,
        CellState.ESCALATED,
        CellState.ERROR,
    },
    CellState.INSTALLING: {CellState.VERIFYING, CellState.ERROR},
    CellState.BUILDING: {
        CellState.EXECUTING,
        CellState.INSTALLING,
        CellState.VERIFYING,
        CellState.ERROR,
    },
    CellState.VERIFYING: {
        CellState.EXECUTING,
        CellState.BUILDING,
        CellState.TOOL_FAILED,
        CellState.ERROR,
    },
    CellState.WAIT_HUMAN: {
        CellState.EXECUTING,
        CellState.ESCALATED,
        CellState.ERROR,
    },
    CellState.COMPLETE: set(),
    CellState.ESCALATED: set(),
    CellState.TOOL_FAILED: {CellState.ESCALATED, CellState.EXECUTING},
    CellState.ERROR: set(),
}


def validate_transition(from_state: CellState, to_state: CellState) -> bool:
    return to_state in VALID_TRANSITIONS.get(from_state, set())


def ensure_transition(from_state: CellState, to_state: CellState) -> None:
    if not validate_transition(from_state, to_state):
        raise ValueError(f"Invalid state transition: {from_state.value} -> {to_state.value}")
