import pytest

from cell.runtime.state import VALID_TRANSITIONS, ensure_transition, validate_transition
from cell.types import CellState


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        (state, target)
        for state, targets in VALID_TRANSITIONS.items()
        for target in targets
    ],
)
def test_every_valid_transition(from_state: CellState, to_state: CellState) -> None:
    assert validate_transition(from_state, to_state) is True
    ensure_transition(from_state, to_state)


@pytest.mark.parametrize("state", [CellState.COMPLETE, CellState.ESCALATED, CellState.ERROR])
def test_terminal_states_have_no_outgoing_transitions(state: CellState) -> None:
    assert VALID_TRANSITIONS[state] == set()


def test_invalid_transition_raises_error() -> None:
    assert validate_transition(CellState.INITIALIZING, CellState.COMPLETE) is False
    with pytest.raises(ValueError):
        ensure_transition(CellState.INITIALIZING, CellState.COMPLETE)


def test_happy_path_sequence() -> None:
    sequence = [CellState.INITIALIZING, CellState.EXECUTING, CellState.COMPLETE]
    for from_state, to_state in zip(sequence, sequence[1:]):
        ensure_transition(from_state, to_state)


def test_tool_build_loop_sequence() -> None:
    sequence = [
        CellState.INITIALIZING,
        CellState.EXECUTING,
        CellState.DIAGNOSING,
        CellState.BUILDING,
        CellState.VERIFYING,
        CellState.EXECUTING,
        CellState.COMPLETE,
    ]
    for from_state, to_state in zip(sequence, sequence[1:]):
        ensure_transition(from_state, to_state)


def test_public_install_sequence() -> None:
    sequence = [
        CellState.INITIALIZING,
        CellState.EXECUTING,
        CellState.DIAGNOSING,
        CellState.INSTALLING,
        CellState.VERIFYING,
        CellState.EXECUTING,
        CellState.COMPLETE,
    ]
    for from_state, to_state in zip(sequence, sequence[1:]):
        ensure_transition(from_state, to_state)


def test_escalation_path_sequence() -> None:
    sequence = [
        CellState.INITIALIZING,
        CellState.EXECUTING,
        CellState.DIAGNOSING,
        CellState.ESCALATED,
    ]
    for from_state, to_state in zip(sequence, sequence[1:]):
        ensure_transition(from_state, to_state)


def test_tool_failure_path_sequence() -> None:
    sequence = [
        CellState.INITIALIZING,
        CellState.EXECUTING,
        CellState.DIAGNOSING,
        CellState.BUILDING,
        CellState.VERIFYING,
        CellState.BUILDING,
        CellState.VERIFYING,
        CellState.TOOL_FAILED,
    ]
    for from_state, to_state in zip(sequence, sequence[1:]):
        ensure_transition(from_state, to_state)
