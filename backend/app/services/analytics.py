import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.domains.scoring import calculate_task_overall, project_overall_band
from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptWritingScore,
    Question,
    TestSession,
    TestVersion,
)
from app.models.enums import AttemptStatus, EventType, ModuleType, TestSessionStatus
from app.schemas.analytics import (
    AnalyticsAttemptOption,
    AnalyticsDashboard,
    AttemptComparison,
    AttemptComparisonSide,
    BandTrendPoint,
    ContentTiming,
    LatestMockSummary,
    QuestionTypeAccuracy,
    SkillBandSummary,
    WritingCriteriaComparison,
)

ACTIVE_STATUSES = {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED}
NAVIGATION_EVENTS = {
    EventType.PASSAGE_CHANGED,
    EventType.LISTENING_PART_CHANGED,
    EventType.WRITING_TASK_CHANGED,
}


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dashboard(self, skill: ModuleType | None = None) -> AnalyticsDashboard:
        attempts = await self._attempts()
        finalized = [item for item in attempts if item.status not in ACTIVE_STATUSES]
        filtered = [item for item in finalized if skill is None or item.module_type == skill]
        time_attempts = [item for item in attempts if skill is None or item.module_type == skill]
        band_attempts = [item for item in filtered if item.band_score is not None]
        bands: dict[str, SkillBandSummary] = {}
        for module in ModuleType:
            candidates = [item for item in finalized if item.module_type == module and item.band_score is not None]
            candidates.sort(key=lambda item: item.finished_at or item.started_at)
            values = [float(item.band_score) for item in candidates if item.band_score is not None]
            bands[module.value] = SkillBandSummary(
                latest=values[-1] if values else None,
                best=max(values) if values else None,
                average=round(sum(values) / len(values), 2) if values else None,
            )
        question_types = self._question_type_accuracy(filtered)
        sessions = await self._sessions()
        completed_sessions = [item for item in sessions if item.status == TestSessionStatus.COMPLETED]
        latest_mock = self._latest_mock(completed_sessions)
        trends = [
            BandTrendPoint(
                attempt_id=item.id,
                skill=item.module_type,
                band_score=float(item.band_score),
                attempted_at=item.finished_at or item.started_at,
                test_title=item.test_version.test.title,
                version_number=item.test_version.version_number,
            )
            for item in sorted(band_attempts, key=lambda row: row.finished_at or row.started_at)
        ]
        elapsed = [self._active_elapsed(item) for item in time_attempts]
        latest_overall = self._latest_project_overall(finalized)
        return AnalyticsDashboard(
            total_finalized_attempts=len(filtered),
            total_active_seconds=sum(elapsed),
            average_attempt_seconds=(round(sum(elapsed) / len(elapsed), 1) if elapsed else None),
            bands=bands,
            completed_full_mocks=len(completed_sessions),
            latest_project_overall=latest_overall,
            latest_full_mock=latest_mock,
            trends=trends,
            question_types=question_types,
            weak_areas=sorted(
                [item for item in question_types if item.attempted >= 5 and item.accuracy is not None],
                key=lambda item: item.accuracy or 0,
            ),
            attempts=[
                AnalyticsAttemptOption(
                    attempt_id=item.id,
                    skill=item.module_type,
                    label=f"{item.test_version.test.title} · V{item.test_version.version_number} · {item.module_type.value.title()}",
                    band_score=float(item.band_score) if item.band_score is not None else None,
                    finished_at=item.finished_at or item.started_at,
                )
                for item in sorted(filtered, key=lambda row: row.finished_at or row.started_at, reverse=True)
            ],
            content_timing=self._content_timing(filtered),
        )

    async def compare(self, left_id: uuid.UUID, right_id: uuid.UUID) -> AttemptComparison:
        attempts = {item.id: item for item in await self._attempts() if item.status not in ACTIVE_STATUSES}
        left = attempts.get(left_id)
        right = attempts.get(right_id)
        if left is None or right is None:
            raise AppError(
                "ANALYTICS_ATTEMPT_NOT_FOUND",
                "Both comparison attempts must exist and be finalized.",
                404,
            )
        return AttemptComparison(
            same_skill=left.module_type == right.module_type,
            same_test_version=left.test_version_id == right.test_version_id,
            left=self._comparison_side(left),
            right=self._comparison_side(right),
        )

    async def _attempts(self) -> list[Attempt]:
        rows = await self.session.scalars(
            select(Attempt)
            .options(
                selectinload(Attempt.test_version).selectinload(TestVersion.test),
                selectinload(Attempt.answers)
                .selectinload(AttemptAnswer.question)
                .selectinload(Question.question_group),
                selectinload(Attempt.events),
                selectinload(Attempt.writing_scores).selectinload(AttemptWritingScore.writing_task),
            )
            .order_by(Attempt.started_at)
        )
        return list(rows)

    async def _sessions(self) -> list[TestSession]:
        rows = await self.session.scalars(
            select(TestSession)
            .options(
                selectinload(TestSession.attempts),
                selectinload(TestSession.test_version).selectinload(TestVersion.test),
            )
            .order_by(TestSession.started_at)
        )
        return list(rows)

    @staticmethod
    def _question_type_accuracy(attempts: list[Attempt]) -> list[QuestionTypeAccuracy]:
        totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for attempt in attempts:
            if attempt.module_type not in {ModuleType.READING, ModuleType.LISTENING}:
                continue
            for answer in attempt.answers:
                question_type = answer.question.question_group.question_type
                totals[question_type][0] += 1
                totals[question_type][1] += int(answer.is_correct is True)
        return [
            QuestionTypeAccuracy(
                question_type=question_type,
                attempted=attempted,
                correct=correct,
                incorrect=attempted - correct,
                accuracy=round(correct * 100 / attempted, 1) if attempted else None,
            )
            for question_type, (attempted, correct) in sorted(totals.items())
        ]

    @staticmethod
    def _content_timing(attempts: list[Attempt]) -> list[ContentTiming]:
        result: list[ContentTiming] = []
        for attempt in attempts:
            events = sorted(
                [event for event in attempt.events if event.event_type in NAVIGATION_EVENTS],
                key=lambda item: item.created_at,
            )
            for index, event in enumerate(events):
                start = int(event.event_metadata.get("active_elapsed_seconds", 0))
                end = (
                    int(events[index + 1].event_metadata.get("active_elapsed_seconds", start))
                    if index + 1 < len(events)
                    else attempt.elapsed_seconds or start
                )
                target = event.event_metadata.get("target_id")
                if target:
                    result.append(
                        ContentTiming(
                            attempt_id=attempt.id,
                            kind=str(event.event_metadata.get("kind", event.event_type.value)),
                            target_id=uuid.UUID(str(target)),
                            active_seconds=max(0, end - start),
                        )
                    )
        return result

    @staticmethod
    def _latest_project_overall(attempts: list[Attempt]) -> float | None:
        by_version: dict[uuid.UUID, list[Attempt]] = defaultdict(list)
        for attempt in attempts:
            by_version[attempt.test_version_id].append(attempt)
        candidates: list[tuple[object, float]] = []
        for rows in by_version.values():
            latest = {
                module: max(
                    (item for item in rows if item.module_type == module),
                    key=lambda item: item.finished_at or item.started_at,
                    default=None,
                )
                for module in ModuleType
            }
            overall = project_overall_band(
                latest[ModuleType.READING].band_score if latest[ModuleType.READING] else None,
                latest[ModuleType.LISTENING].band_score if latest[ModuleType.LISTENING] else None,
                latest[ModuleType.WRITING].band_score if latest[ModuleType.WRITING] else None,
            )
            if overall is not None:
                candidates.append((max(item.finished_at or item.started_at for item in rows), float(overall)))
        return max(candidates, key=lambda item: item[0])[1] if candidates else None

    @staticmethod
    def _latest_mock(sessions: list[TestSession]) -> LatestMockSummary | None:
        if not sessions:
            return None
        item = max(sessions, key=lambda row: row.finished_at or row.started_at)
        bands = {attempt.module_type: attempt.band_score for attempt in item.attempts}
        overall = project_overall_band(
            bands.get(ModuleType.READING), bands.get(ModuleType.LISTENING), bands.get(ModuleType.WRITING)
        )
        return LatestMockSummary(
            session_id=item.id,
            test_title=item.test_version.test.title,
            finished_at=item.finished_at or item.started_at,
            reading_band=float(bands[ModuleType.READING]) if bands.get(ModuleType.READING) is not None else None,
            listening_band=float(bands[ModuleType.LISTENING]) if bands.get(ModuleType.LISTENING) is not None else None,
            writing_band=float(bands[ModuleType.WRITING]) if bands.get(ModuleType.WRITING) is not None else None,
            overall_band=float(overall) if overall is not None else None,
        )

    def _comparison_side(self, attempt: Attempt) -> AttemptComparisonSide:
        accuracy = self._question_type_accuracy([attempt])
        attempted = sum(item.attempted for item in accuracy)
        correct = sum(item.correct for item in accuracy)
        writing = None
        if attempt.module_type == ModuleType.WRITING:
            task_scores = {
                score.writing_task.task_number: calculate_task_overall(
                    score.ta, score.cc, score.lr, score.gra
                )
                for score in attempt.writing_scores
            }
            scores = attempt.writing_scores
            writing = WritingCriteriaComparison(
                task1_overall=float(task_scores[1]) if 1 in task_scores else None,
                task2_overall=float(task_scores[2]) if 2 in task_scores else None,
                ta=self._criterion_average(scores, "ta"),
                cc=self._criterion_average(scores, "cc"),
                lr=self._criterion_average(scores, "lr"),
                gra=self._criterion_average(scores, "gra"),
            )
        return AttemptComparisonSide(
            attempt_id=attempt.id,
            skill=attempt.module_type,
            test_title=attempt.test_version.test.title,
            version_number=attempt.test_version.version_number,
            band_score=float(attempt.band_score) if attempt.band_score is not None else None,
            raw_score=attempt.raw_score,
            max_score=attempt.max_score,
            elapsed_seconds=attempt.elapsed_seconds,
            accuracy=round(correct * 100 / attempted, 1) if attempted else None,
            question_types=accuracy,
            writing=writing,
        )

    @staticmethod
    def _criterion_average(scores: list[AttemptWritingScore], name: str) -> float | None:
        if not scores:
            return None
        values = [Decimal(getattr(score, name)) for score in scores]
        return float(sum(values, start=Decimal("0")) / len(values))

    @staticmethod
    def _active_elapsed(attempt: Attempt) -> int:
        if attempt.elapsed_seconds is not None:
            return attempt.elapsed_seconds
        from app.domains.timers import TimerService

        return TimerService.snapshot(
            mode=attempt.timer_mode,
            started_at=attempt.started_at,
            limit_seconds=attempt.timer_limit_seconds,
            paused_at=attempt.paused_at,
            total_paused_seconds=attempt.total_paused_seconds,
        ).elapsed_seconds
