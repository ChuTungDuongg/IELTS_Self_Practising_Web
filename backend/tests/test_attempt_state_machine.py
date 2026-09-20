import pytest

from app.core.exceptions import AppError
from app.domains.attempts import AttemptStateMachine
from app.models.enums import AttemptStatus


@pytest.mark.parametrize(
    "target",
    [
        AttemptStatus.PAUSED,
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


def test_paused_attempt_can_only_resume() -> None:
    AttemptStateMachine.ensure_transition(AttemptStatus.PAUSED, AttemptStatus.IN_PROGRESS)

    with pytest.raises(AppError) as caught:
        AttemptStateMachine.ensure_transition(AttemptStatus.PAUSED, AttemptStatus.SUBMITTED)
    assert caught.value.code == "INVALID_ATTEMPT_TRANSITION"


@pytest.mark.parametrize(
    "finalized",
    [
        AttemptStatus.SUBMITTED,
        AttemptStatus.AUTO_SUBMITTED,
        AttemptStatus.INTERRUPTED,
        AttemptStatus.ABANDONED,
    ],
)
def test_finalized_attempt_cannot_pause_or_resume(finalized: AttemptStatus) -> None:
    for target in (AttemptStatus.PAUSED, AttemptStatus.IN_PROGRESS):
        with pytest.raises(AppError):
            AttemptStateMachine.ensure_transition(finalized, target)
