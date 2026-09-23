import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.domains.scoring import project_overall_band
from app.domains.timers import TimerService
from app.models import Attempt, QuestionGroup, Test, TestModule, TestSession, TestVersion
from app.models.enums import (
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

MODULE_ORDER = (ModuleType.LISTENING, ModuleType.READING, ModuleType.WRITING)
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

    async def start(self, test_version_id: uuid.UUID) -> TestSessionStartResponse:
        now = TimerService.now()
        async with self.session.begin():
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
                user_id=self.user_id,
                test_version_id=version.id,
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
                and current.module_type == ModuleType.WRITING
                and current.status in FINAL_STATUSES
                and test_session.status == TestSessionStatus.IN_PROGRESS
            ):
                test_session.status = TestSessionStatus.COMPLETED
                test_session.finished_at = current.finished_at or TimerService.now()
            return await self._present(test_session)

    async def advance(self, session_id: uuid.UUID) -> TestSessionResponse:
        now = TimerService.now()
        async with self.session.begin():
            test_session = await self._require(session_id, for_update=True)
            if test_session.status != TestSessionStatus.IN_PROGRESS:
                return await self._present(test_session)
            current = self._current_attempt(test_session)
            if current is None:
                next_module = ModuleType.LISTENING
            else:
                await self._synchronize_timeout(current)
                if current.status not in FINAL_STATUSES:
                    raise AppError(
                        "FULL_MOCK_MODULE_ACTIVE",
                        "Finish the current module before continuing.",
                        409,
                    )
                current_index = MODULE_ORDER.index(current.module_type)
                if current_index == len(MODULE_ORDER) - 1:
                    test_session.status = TestSessionStatus.COMPLETED
                    test_session.finished_at = current.finished_at or now
                    return await self._present(test_session)
                next_module = MODULE_ORDER[current_index + 1]
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
            statement = statement.with_for_update()
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
            timer_mode=TimerMode.COUNTDOWN,
            timer_limit_seconds=module.recommended_duration_seconds,
            started_at=now,
            last_active_at=now,
            status=AttemptStatus.IN_PROGRESS,
        )

    @staticmethod
    def _current_attempt(test_session: TestSession) -> Attempt | None:
        if not test_session.attempts:
            return None
        return max(test_session.attempts, key=lambda item: MODULE_ORDER.index(item.module_type))

    async def _synchronize_timeout(self, attempt: Attempt) -> None:
        from app.services.attempts import AttemptService

        await AttemptService(self.session, self.user_id)._synchronize_state(
            attempt, TimerService.now()
        )

    @staticmethod
    def _attempt_response(attempt: Attempt, now=None) -> AttemptResponse:
        from app.services.attempts import AttemptService

        return AttemptService._to_response(attempt, now)

    async def _present(self, test_session: TestSession) -> TestSessionResponse:
        current = self._current_attempt(test_session)
        current_index = MODULE_ORDER.index(current.module_type) if current is not None else -1
        current_final = current is not None and current.status in FINAL_STATUSES
        next_module = (
            MODULE_ORDER[current_index + 1]
            if current_final and current_index + 1 < len(MODULE_ORDER)
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
        overall = project_overall_band(
            bands.get(ModuleType.READING),
            bands.get(ModuleType.LISTENING),
            bands.get(ModuleType.WRITING),
        )
        warnings: list[str] = []
        for module in test_session.test_version.modules:
            if module.module_type not in {ModuleType.READING, ModuleType.LISTENING}:
                continue
            count = sum(len(group.questions) for group in module.question_groups)
            if count != 40:
                warnings.append(
                    f"{module.module_type.value.title()} has {count} questions. An official band will not be calculated."
                )
        attempts = sorted(
            test_session.attempts, key=lambda item: MODULE_ORDER.index(item.module_type)
        )
        return TestSessionResponse(
            session_id=test_session.id,
            test_version_id=test_session.test_version_id,
            test_title=test_session.test_version.test.title,
            version_number=test_session.test_version.version_number,
            status=test_session.status,
            started_at=test_session.started_at,
            finished_at=test_session.finished_at,
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
