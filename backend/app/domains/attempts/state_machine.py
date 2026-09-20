from app.core.exceptions import AppError
from app.models.enums import AttemptStatus


class AttemptStateMachine:
    _allowed: dict[AttemptStatus, frozenset[AttemptStatus]] = {
        AttemptStatus.IN_PROGRESS: frozenset(
            {
                AttemptStatus.PAUSED,
                AttemptStatus.SUBMITTED,
                AttemptStatus.AUTO_SUBMITTED,
                AttemptStatus.INTERRUPTED,
                AttemptStatus.ABANDONED,
            }
        ),
        AttemptStatus.PAUSED: frozenset({AttemptStatus.IN_PROGRESS}),
        AttemptStatus.SUBMITTED: frozenset(),
        AttemptStatus.AUTO_SUBMITTED: frozenset(),
        AttemptStatus.INTERRUPTED: frozenset(),
        AttemptStatus.ABANDONED: frozenset(),
    }

    @classmethod
    def ensure_transition(cls, current: AttemptStatus, target: AttemptStatus) -> None:
        if target not in cls._allowed[current]:
            raise AppError(
                "INVALID_ATTEMPT_TRANSITION",
                f"Attempt cannot move from {current.value} to {target.value}.",
                409,
            )
