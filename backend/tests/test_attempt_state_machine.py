import pytest

from app.core.exceptions import AppError
from app.domains.attempts import AttemptStateMachine
from app.models.enums import AttemptStatus


@pytest.mark.parametrize(
    "target",
    [
        AttemptStatus.SUBMITTED,
        AttemptStatus.AUTO_SUBMITTED,
        AttemptStatus.INTERRUPTED,
        AttemptStatus.ABANDONED,
    ],
)
def test_in_progress_can_reach_terminal_states(target: AttemptStatus) -> None:
    AttemptStateMachine.ensure_transition(AttemptStatus.IN_PROGRESS, target)


def test_terminal_state_cannot_transition_again() -> None:
    with pytest.raises(AppError) as caught:
        AttemptStateMachine.ensure_transition(AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED)
    assert caught.value.code == "INVALID_ATTEMPT_TRANSITION"
