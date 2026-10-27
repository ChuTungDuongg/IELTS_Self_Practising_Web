import uuid
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.domains.questions.numbering import group_slots
from app.domains.scoring import legacy_three_skill_overall_band, project_overall_band
from app.domains.timers import TimerService
from app.models import Attempt, QuestionGroup, Test, TestModule, TestSession, TestVersion
from app.models.enums import (
    AttemptScope,
    AttemptStatus,
    ModuleType,
    TestSessionStatus,
    TimerMode,
    VersionStatus,
)
from app.schemas.attempts import AttemptResponse
from app.schemas.test_sessions import (
    SessionAttemptSummary,
    TestSessionResponse,
    TestSessionStartResponse,
)

LEGACY_MODULE_ORDER = (ModuleType.LISTENING, ModuleType.READING, ModuleType.WRITING)
MODULE_ORDER = (*LEGACY_MODULE_ORDER, ModuleType.SPEAKING)
FINAL_STATUSES = {
    AttemptStatus.SUBMITTED,
    AttemptStatus.AUTO_SUBMITTED,
    AttemptStatus.INTERRUPTED,
    AttemptStatus.ABANDONED,
}


class TestSessionService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID | None = None) -> None:
        self.session = session
        self.user_id = user_id or session.info.get("current_user_id")
        if not isinstance(self.user_id, uuid.UUID):
            raise ValueError("TestSessionService requires an authenticated user id")

    async def start(
        self, test_version_id: uuid.UUID, *, _classroom_assignment_id: uuid.UUID | None = None
    ) -> TestSessionStartResponse:
        now = TimerService.now()
        async with self.session.begin():
            if _classroom_assignment_id is not None:
                from app.schemas.assignment_targets import AssignmentTarget
                from app.services.classroom_assignments import require_assignment_start

                await require_assignment_start(
                    self.session,
                    self.user_id,
                    _classroom_assignment_id,
                    test_version_id,
                    target=AssignmentTarget(mode="FULL_MOCK"),
                )
            else:
                from app.models import User
                from app.services.access_policy import AccessPolicy

                actor = await self.session.get(User, self.user_id)
                if actor is None:
                    raise AppError("ACCOUNT_INACTIVE", "This account is inactive.", 403)
                policy = AccessPolicy(self.session, actor)
                await policy.lock_actor()
                try:
                    candidate = await policy.lock_version(test_version_id)
                except AppError as error:
                    if error.status_code != 404:
                        raise
                    raise AppError(
                        "FULL_MOCK_VERSION_UNAVAILABLE", "This version is unavailable.", 422
                    ) from error
                if not await policy.version_access(candidate):
                    raise AppError(
                        "FULL_MOCK_VERSION_UNAVAILABLE", "This version is unavailable.", 422
                    )
            version = await self._load_version(test_version_id, for_update=True)
            if version is None or version.status != VersionStatus.PUBLISHED:
                raise AppError(
                    "FULL_MOCK_VERSION_UNAVAILABLE",
                    "Full Mock requires an available published test version.",
                    422,
                )
            modules = {module.module_type: module for module in version.modules}
            missing = [module.value.title() for module in MODULE_ORDER if module not in modules]
            if missing:
                raise AppError(
                    "FULL_MOCK_MODULES_MISSING",
                    f"Full Mock unavailable: {', '.join(missing)} module is missing.",
                    422,
                )
            missing_duration = [
                module.value.title()
                for module in MODULE_ORDER
                if not modules[module].recommended_duration_seconds
                or modules[module].recommended_duration_seconds <= 0
            ]
            if missing_duration:
                raise AppError(
                    "FULL_MOCK_DURATION_MISSING",
                    "Full Mock unavailable: recommended duration is missing for "
                    + ", ".join(missing_duration)
                    + ".",
                    422,
                )
            test_session = TestSession(
                classroom_assignment_id=_classroom_assignment_id,
                user_id=self.user_id,
                test_version_id=version.id,
                module_order_json=[module.value for module in MODULE_ORDER],
                status=TestSessionStatus.IN_PROGRESS,
                started_at=now,
            )
            self.session.add(test_session)
            await self.session.flush()
            attempt = self._new_attempt(test_session, modules[ModuleType.LISTENING], now)
            self.session.add(attempt)
            await self.session.flush()
            session_id = test_session.id
            attempt_response = self._attempt_response(attempt, now)
        response = await self.get(session_id)
        return TestSessionStartResponse(session=response, current_attempt=attempt_response)

    async def get(self, session_id: uuid.UUID) -> TestSessionResponse:
        async with self.session.begin():
            test_session = await self._require(session_id, for_update=True)
            current = self._current_attempt(test_session)
            if current is not None and current.status == AttemptStatus.IN_PROGRESS:
                await self._synchronize_timeout(current)
            if (
                current is not None
                and current.module_type == self._module_order(test_session)[-1]
                and current.status in FINAL_STATUSES
                and test_session.status == TestSessionStatus.IN_PROGRESS
            ):
                test_session.status = TestSessionStatus.COMPLETED
                test_session.finished_at = current.finished_at or TimerService.now()
            return await self._present(test_session)

    async def delete(self, session_id: uuid.UUID) -> None:
        async with self.session.begin():
            test_session = await self._require(session_id, for_update=True)
            if test_session.classroom_assignment_id or any(
                attempt.classroom_assignment_id for attempt in test_session.attempts
            ):
                raise AppError(
                    "ASSIGNMENT_HISTORY_RETAINED", "Assignment Full Mock history is retained.", 409
                )
            from app.services.speaking_media import queue_media_cleanup

            await queue_media_cleanup(
                self.session, [attempt.id for attempt in test_session.attempts]
            )
            await self.session.execute(delete(TestSession).where(TestSession.id == test_session.id))

    async def advance(self, session_id: uuid.UUID) -> TestSessionResponse:
        now = TimerService.now()
        async with self.session.begin():
            test_session = await self._require(session_id, for_update=True)
            if test_session.status != TestSessionStatus.IN_PROGRESS:
                return await self._present(test_session)
            module_order = self._module_order(test_session)
            current = self._current_attempt(test_session)
            if current is None:
                next_module = module_order[0]
            else:
                await self._synchronize_timeout(current)
                if current.status not in FINAL_STATUSES:
                    raise AppError(
                        "FULL_MOCK_MODULE_ACTIVE",
                        "Finish the current module before continuing.",
                        409,
                    )
                current_index = module_order.index(current.module_type)
                if current_index == len(module_order) - 1:
                    test_session.status = TestSessionStatus.COMPLETED
                    test_session.finished_at = current.finished_at or now
                    return await self._present(test_session)
                next_module = module_order[current_index + 1]
            existing = next(
                (
                    attempt
                    for attempt in test_session.attempts
                    if attempt.module_type == next_module
                ),
                None,
            )
            if existing is None:
                module = next(
                    item
                    for item in test_session.test_version.modules
                    if item.module_type == next_module
                )
                existing = self._new_attempt(test_session, module, now)
                self.session.add(existing)
                await self.session.flush()
            return await self._present(test_session)

    async def _load_version(
        self, version_id: uuid.UUID, *, for_update: bool = False
    ) -> TestVersion | None:
        statement = (
            select(TestVersion)
            .join(Test, TestVersion.test_id == Test.id)
            .where(TestVersion.id == version_id, Test.archived_at.is_(None))
            .options(
                selectinload(TestVersion.test),
                selectinload(TestVersion.modules)
                .selectinload(TestModule.question_groups)
                .selectinload(QuestionGroup.questions),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def _require(self, session_id: uuid.UUID, *, for_update: bool = False) -> TestSession:
        statement = (
            select(TestSession)
            .where(TestSession.id == session_id, TestSession.user_id == self.user_id)
            .options(
                selectinload(TestSession.attempts),
                selectinload(TestSession.test_version).selectinload(TestVersion.test),
                selectinload(TestSession.test_version)
                .selectinload(TestVersion.modules)
                .selectinload(TestModule.question_groups)
                .selectinload(QuestionGroup.questions),
            )
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        result = await self.session.scalar(statement)
        if result is None:
            raise AppError("TEST_SESSION_NOT_FOUND", "The Full Mock session does not exist.", 404)
        return result

    @staticmethod
    def _new_attempt(test_session: TestSession, module: TestModule, now) -> Attempt:
        return Attempt(
            user_id=test_session.user_id,
            test_version_id=test_session.test_version_id,
            test_session=test_session,
            module_type=module.module_type,
            speaking_mode="EXAM" if module.module_type == ModuleType.SPEAKING else None,
            scope=AttemptScope.FULL_MODULE,
            # Speaking uses authored phase deadlines and bounded recovery, rather
            # than consuming a generic module countdown during microphone setup.
            timer_mode=TimerMode.COUNT_UP
            if module.module_type == ModuleType.SPEAKING
            else TimerMode.COUNTDOWN,
            timer_limit_seconds=None
            if module.module_type == ModuleType.SPEAKING
            else module.recommended_duration_seconds,
            started_at=now,
            last_active_at=now,
            status=AttemptStatus.IN_PROGRESS,
        )

    @staticmethod
    def _module_order(test_session: TestSession) -> tuple[ModuleType, ...]:
        """Use persisted session semantics; never infer them from version coverage."""
        order = tuple(ModuleType(item) for item in test_session.module_order_json)
        if order not in {LEGACY_MODULE_ORDER, MODULE_ORDER}:
            raise AppError("FULL_MOCK_ORDER_INVALID", "The Full Mock module order is invalid.", 409)
        return order

    @staticmethod
    def _current_attempt(test_session: TestSession) -> Attempt | None:
        if not test_session.attempts:
            return None
        module_order = TestSessionService._module_order(test_session)
        if any(item.module_type not in module_order for item in test_session.attempts):
            raise AppError("FULL_MOCK_ORDER_INVALID", "The Full Mock module order is invalid.", 409)
        return max(test_session.attempts, key=lambda item: module_order.index(item.module_type))

    async def _synchronize_timeout(self, attempt: Attempt) -> None:
        from app.services.attempts import AttemptService

        service = AttemptService(self.session, self.user_id)
        # The parent is already locked. Refresh and lock the child before
        # scoring/finalizing, preserving the parent's loaded attempt collection.
        await self.session.refresh(
            attempt,
            attribute_names=[column.key for column in Attempt.__mapper__.column_attrs],
            with_for_update=True,
        )
        await service._synchronize_state(attempt, TimerService.now())

    @staticmethod
    def _attempt_response(attempt: Attempt, now=None) -> AttemptResponse:
        from app.services.attempts import AttemptService

        return AttemptService._to_response(attempt, now)

    async def _present(self, test_session: TestSession) -> TestSessionResponse:
        module_order = self._module_order(test_session)
        current = self._current_attempt(test_session)
        current_index = module_order.index(current.module_type) if current is not None else -1
        current_final = current is not None and current.status in FINAL_STATUSES
        next_module = (
            module_order[current_index + 1]
            if current_final and current_index + 1 < len(module_order)
            else None
        )
        current_module = (
            None
            if test_session.status == TestSessionStatus.COMPLETED
            else (
                next_module
                if current_final
                else current.module_type
                if current is not None
                else ModuleType.LISTENING
            )
        )
        bands = {attempt.module_type: attempt.band_score for attempt in test_session.attempts}
        score_inputs = (
            bands.get(ModuleType.READING),
            bands.get(ModuleType.LISTENING),
            bands.get(ModuleType.WRITING),
        )
        overall = (
            legacy_three_skill_overall_band(*score_inputs)
            if module_order == LEGACY_MODULE_ORDER
            else project_overall_band(*score_inputs, bands.get(ModuleType.SPEAKING))
        )
        warnings: list[str] = []
        for module in test_session.test_version.modules:
            if module.module_type not in {ModuleType.READING, ModuleType.LISTENING}:
                continue
            count = sum(
                len(group_slots(group.question_type, group.questions))
                for group in module.question_groups
            )
            if count != 40:
                warnings.append(
                    f"{module.module_type.value.title()} has {count} questions. An official band will not be calculated."
                )
        attempts = sorted(
            test_session.attempts, key=lambda item: module_order.index(item.module_type)
        )
        return TestSessionResponse(
            session_id=test_session.id,
            test_version_id=test_session.test_version_id,
            test_title=test_session.test_version.test.title,
            version_number=test_session.test_version.version_number,
            status=test_session.status,
            started_at=test_session.started_at,
            finished_at=test_session.finished_at,
            module_order=list(module_order),
            current_module=current_module,
            next_module=next_module,
            current_attempt=(
                self._attempt_response(current)
                if current is not None and current.status not in FINAL_STATUSES
                else None
            ),
            attempts=[
                SessionAttemptSummary(
                    attempt_id=item.id,
                    module=item.module_type,
                    status=item.status.value,
                    band_score=float(item.band_score) if item.band_score is not None else None,
                    raw_score=item.raw_score,
                    max_score=item.max_score,
                    elapsed_seconds=item.elapsed_seconds,
                )
                for item in attempts
            ],
            warnings=warnings,
            overall_band_score=float(overall) if isinstance(overall, Decimal) else overall,
        )
