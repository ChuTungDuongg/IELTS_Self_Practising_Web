"""Content scope policy shared by attempt reads, mutations and grading eligibility."""

from uuid import UUID

from sqlalchemy import false, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domains.timers.service import COUNTDOWN_PRESETS
from app.models import (
    Attempt,
    ListeningPart,
    QuestionGroup,
    ReadingPassage,
    TestModule,
    WritingTask,
)
from app.models.enums import AttemptScope, ModuleType, TimerMode
from app.schemas.attempts import AttemptCreate, FocusedUnitResponse

UNITS = {
    "READING_PASSAGE": (ModuleType.READING, ReadingPassage, "focused_reading_passage"),
    "LISTENING_PART": (ModuleType.LISTENING, ListeningPart, "focused_listening_part"),
    "WRITING_TASK": (ModuleType.WRITING, WritingTask, "focused_writing_task"),
}
FOCUSED_PRESETS = {
    ModuleType.READING: frozenset({1200, 1500, 1800}),
    ModuleType.LISTENING: frozenset({600, 900, 1200}),
    ModuleType.WRITING: frozenset({1200, 1500, 1800, 2100, 2400}),
}


def validate_start_scope(data: AttemptCreate) -> None:
    if data.scope == AttemptScope.FULL_MODULE:
        if data.focused_unit is not None:
            raise AppError(
                "INVALID_ATTEMPT_SCOPE", "Full-module attempts cannot select a focused unit.", 422
            )
    elif data.focused_unit is None:
        raise AppError("FOCUSED_UNIT_REQUIRED", "Select one unit for focused practice.", 422)
    elif UNITS[data.focused_unit.kind][0] != data.module:
        raise AppError(
            "FOCUSED_UNIT_INVALID",
            "The selected unit is not available for this module and version.",
            422,
        )
    # This policy is only for standalone creation. Full Mock uses its frozen
    # module durations through TestSessionService and always has FULL_MODULE scope.
    presets = (
        FOCUSED_PRESETS[data.module]
        if data.scope == AttemptScope.FOCUSED_UNIT
        else COUNTDOWN_PRESETS
    )
    if data.timer.mode == TimerMode.COUNTDOWN and data.timer.duration_seconds not in presets:
        raise AppError(
            "INVALID_TIMER_PRESET",
            "The countdown duration is not a preset for this attempt scope and module.",
            422,
        )


async def resolve_focused_target(
    session: AsyncSession, data: AttemptCreate, module_id: UUID
) -> dict:
    if data.focused_unit is None:
        return {}
    _, model, field = UNITS[data.focused_unit.kind]
    target = await session.scalar(
        select(model).where(model.id == data.focused_unit.id, model.module_id == module_id)
    )
    if target is None:
        # Missing, foreign-version and foreign-module IDs are indistinguishable.
        raise AppError(
            "FOCUSED_UNIT_INVALID",
            "The selected unit is not available for this module and version.",
            422,
        )
    if data.module == ModuleType.LISTENING:
        audio_asset_id = await session.scalar(
            select(TestModule.audio_asset_id).where(TestModule.id == module_id)
        )
        start, end = target.audio_start_seconds, target.audio_end_seconds
        if audio_asset_id is None or start is None or end is None or start < 0 or end <= start:
            raise AppError(
                "FOCUSED_LISTENING_AUDIO_UNAVAILABLE",
                "Focused Listening requires a recording and a configured section audio range.",
                422,
            )
    return {f"{field}_id": target.id}


class AttemptScopeGuard:
    def __init__(self, attempt: Attempt):
        self.attempt = attempt

    @property
    def focused(self) -> bool:
        return self.attempt.scope == AttemptScope.FOCUSED_UNIT

    def allows_unit(self, kind: str, target_id: UUID) -> bool:
        module, _, field = UNITS[kind]
        return self.attempt.module_type == module and (
            not self.focused or getattr(self.attempt, f"{field}_id") == target_id
        )

    def require_unit(self, kind: str, target_id: UUID) -> None:
        if not self.allows_unit(kind, target_id):
            self._reject()

    def allows_group(self, group: QuestionGroup) -> bool:
        if not self.focused:
            return True
        return (
            self.attempt.module_type == ModuleType.READING
            and group.passage_id == self.attempt.focused_reading_passage_id
        ) or (
            self.attempt.module_type == ModuleType.LISTENING
            and group.listening_part_id == self.attempt.focused_listening_part_id
        )

    def require_group(self, group: QuestionGroup) -> None:
        if not self.allows_group(group):
            self._reject()

    def group_filter(self):
        if not self.focused:
            return true()
        if self.attempt.module_type == ModuleType.READING:
            return QuestionGroup.passage_id == self.attempt.focused_reading_passage_id
        if self.attempt.module_type == ModuleType.LISTENING:
            return QuestionGroup.listening_part_id == self.attempt.focused_listening_part_id
        return false()

    def presentation(self) -> FocusedUnitResponse | None:
        if not self.focused:
            return None
        for kind, (module, _, field) in UNITS.items():
            if self.attempt.module_type == module:
                unit = getattr(self.attempt, field)
                label = (
                    f"Task {unit.task_number}"
                    if kind == "WRITING_TASK"
                    else f"{'Passage' if kind == 'READING_PASSAGE' else 'Section'} {unit.order_index + 1}"
                )
                return FocusedUnitResponse(
                    kind=kind,
                    id=unit.id,
                    order_index=unit.order_index,
                    label=label,
                    title=getattr(unit, "title", None),
                )
        return None

    @staticmethod
    def _reject() -> None:
        raise AppError(
            "ATTEMPT_TARGET_OUT_OF_SCOPE",
            "The target does not belong to this attempt's content scope.",
            422,
        )
