import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.domains.attempts import AttemptStateMachine
from app.domains.questions import question_registry
from app.domains.questions.normalization import (
    normalize_passage_blocks,
    normalize_question_group_payload,
    normalize_response_value,
)
from app.domains.scoring import (
    calculate_final_writing_band,
    calculate_task_overall,
    calculate_weighted_writing_overall,
    listening_raw_to_band,
    project_overall_band,
    reading_raw_to_band,
)
from app.domains.timers import TimerService
from app.domains.writing import count_words
from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptEvent,
    AttemptWritingResponse,
    AttemptWritingScore,
    Highlight,
    Question,
    QuestionFlag,
    QuestionGroup,
    ReadingPassage,
    Test,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.models.enums import (
    AttemptStatus,
    EventType,
    FinishedReason,
    ModuleType,
    VersionStatus,
)
from app.repositories.attempts import AttemptRepository
from app.repositories.tests import TestRepository
from app.schemas.assets import AssetResponse
from app.schemas.attempts import (
    AnswerResponse,
    AttemptCreate,
    AttemptList,
    AttemptResponse,
    AttemptReview,
    HistoryGroup,
    HistoryItem,
    ReviewAnswer,
    WritingResponse,
    WritingReview,
    WritingTaskScore,
    WritingTaskScoreUpdate,
)
from app.schemas.content import (
    AttemptExam,
    ExamListeningPart,
    ExamPassage,
    ExamQuestion,
    ExamQuestionGroup,
    ExamWritingTask,
    FlagResponse,
    HighlightCreate,
    HighlightResponse,
    ListeningReview,
    ReadingReview,
    WritingAttemptReview,
)
from app.services.reading import ReadingService


class AttemptService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AttemptRepository(session)

    async def start(self, data: AttemptCreate) -> AttemptResponse:
        now = TimerService.now()
        async with self.session.begin():
            module = await self.session.scalar(
                select(TestModule)
                .join(TestVersion)
                .join(Test, TestVersion.test_id == Test.id)
                .where(
                    TestVersion.id == data.test_version_id,
                    TestVersion.status == VersionStatus.PUBLISHED,
                    Test.archived_at.is_(None),
                    TestModule.module_type == data.module,
                )
            )
            if module is None:
                raise AppError(
                    "TEST_MODULE_UNAVAILABLE",
                    "The requested module is not available in a published version.",
                    422,
                )
            attempt = Attempt(
                test_version_id=data.test_version_id,
                module_type=data.module,
                timer_mode=data.timer.mode,
                timer_limit_seconds=data.timer.duration_seconds,
                started_at=now,
                last_active_at=now,
                status=AttemptStatus.IN_PROGRESS,
            )
            self.session.add(attempt)
            await self.session.flush()
            attempt_id = attempt.id
        return await self.get(attempt_id)

    async def get(self, attempt_id: uuid.UUID) -> AttemptResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            await self._synchronize_state(attempt, TimerService.now())
            response = self._to_response(attempt)
        return response

    async def record_activity(self, attempt_id: uuid.UUID) -> AttemptResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            await self._ensure_mutable(attempt, now)
            attempt.last_active_at = now
            response = self._to_response(attempt, now)
        return response

    async def pause(self, attempt_id: uuid.UUID) -> AttemptResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            await self._synchronize_state(attempt, now)
            if attempt.status == AttemptStatus.AUTO_SUBMITTED:
                return self._to_response(attempt, now)
            AttemptStateMachine.ensure_transition(attempt.status, AttemptStatus.PAUSED)
            attempt.status = AttemptStatus.PAUSED
            attempt.paused_at = now
            attempt.last_active_at = now
            attempt.finished_at = None
            attempt.finished_reason = None
            response = self._to_response(attempt, now)
        return response

    async def resume(self, attempt_id: uuid.UUID) -> AttemptResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            AttemptStateMachine.ensure_transition(attempt.status, AttemptStatus.IN_PROGRESS)
            if attempt.paused_at is None:
                raise AppError(
                    "INVALID_PAUSE_STATE",
                    "This paused attempt has no pause timestamp.",
                    409,
                )
            pause_duration = max(0, int((now - attempt.paused_at).total_seconds()))
            attempt.total_paused_seconds += pause_duration
            attempt.paused_at = None
            attempt.status = AttemptStatus.IN_PROGRESS
            attempt.last_active_at = now
            response = self._to_response(attempt, now)
        return response

    async def save_answer(
        self, attempt_id: uuid.UUID, question_id: uuid.UUID, value: Any
    ) -> AnswerResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            await self._ensure_mutable(attempt, now)
            question = await self.session.scalar(
                select(Question)
                .join(QuestionGroup)
                .join(TestModule)
                .where(
                    Question.id == question_id,
                    TestModule.test_version_id == attempt.test_version_id,
                    TestModule.module_type == attempt.module_type,
                )
            )
            if question is None:
                raise AppError(
                    "INVALID_QUESTION", "The question does not belong to this attempt.", 422
                )
            group = await self.session.scalar(
                select(QuestionGroup)
                .where(QuestionGroup.id == question.question_group_id)
                .options(selectinload(QuestionGroup.passage))
            )
            assert group is not None
            passage_blocks = (
                normalize_passage_blocks(group.passage.content_json, group.passage.id)
                if group.passage
                else []
            )
            normalized_group_config, normalized_questions = normalize_question_group_payload(
                question_type=group.question_type,
                group_config=group.config,
                questions=[
                    {
                        "id": question.id,
                        "number": question.number,
                        "prompt": question.prompt,
                        "config": question.config,
                        "answer_key": question.answer_key,
                        "explanation": question.explanation,
                        "order_index": question.order_index,
                    }
                ],
                group_id=group.id,
                passage_blocks=passage_blocks,
            )
            normalized_question = normalized_questions[0]
            normalized_value = normalize_response_value(
                question_type=group.question_type,
                value=value,
                raw_group_config=group.config,
                raw_question_config=question.config,
                normalized_group_config=normalized_group_config,
                normalized_question_config=normalized_question["config"],
            )
            validated_value = (
                question_registry.validate_response(group.question_type, normalized_value)
                if question_registry.supports(group.question_type)
                else normalized_value
            )
            is_correct = (
                question_registry.evaluate(
                    group.question_type,
                    normalized_question["answer_key"],
                    validated_value,
                    normalized_question["config"],
                )
                if question_registry.supports(group.question_type)
                else None
            )
            statement = insert(AttemptAnswer).values(
                id=uuid.uuid4(),
                attempt_id=attempt.id,
                question_id=question.id,
                value=validated_value,
                is_correct=is_correct,
                created_at=now,
                updated_at=now,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[AttemptAnswer.attempt_id, AttemptAnswer.question_id],
                set_={
                    "value": validated_value,
                    "is_correct": is_correct,
                    "updated_at": now,
                },
            )
            await self.session.execute(statement)
            self.session.add(
                AttemptEvent(
                    attempt_id=attempt.id,
                    event_type=EventType.ANSWER_CHANGED,
                    question_id=question.id,
                    event_metadata={},
                    created_at=now,
                )
            )
            attempt.last_active_at = now
        return AnswerResponse(
            question_id=question_id,
            value=validated_value,
            is_correct=is_correct,
            saved_at=now,
        )

    async def save_writing_response(
        self, attempt_id: uuid.UUID, writing_task_id: uuid.UUID, content: str
    ) -> WritingResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            await self._ensure_mutable(attempt, now)
            if attempt.module_type != ModuleType.WRITING:
                raise AppError(
                    "WRITING_ATTEMPT_REQUIRED",
                    "Writing responses can only be saved on a Writing attempt.",
                    422,
                )
            task = await self.session.scalar(
                select(WritingTask)
                .join(TestModule)
                .where(
                    WritingTask.id == writing_task_id,
                    TestModule.test_version_id == attempt.test_version_id,
                    TestModule.module_type == ModuleType.WRITING,
                )
            )
            if task is None:
                raise AppError(
                    "INVALID_WRITING_TASK",
                    "The Writing task does not belong to this attempt.",
                    422,
                )
            word_count = count_words(content)
            statement = insert(AttemptWritingResponse).values(
                id=uuid.uuid4(),
                attempt_id=attempt.id,
                writing_task_id=task.id,
                content=content,
                word_count=word_count,
                created_at=now,
                updated_at=now,
            )
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        AttemptWritingResponse.attempt_id,
                        AttemptWritingResponse.writing_task_id,
                    ],
                    set_={
                        "content": content,
                        "word_count": word_count,
                        "updated_at": now,
                    },
                )
            )
            self.session.add(
                AttemptEvent(
                    attempt_id=attempt.id,
                    event_type=EventType.WRITING_UPDATED,
                    event_metadata={"writing_task_id": str(task.id)},
                    created_at=now,
                )
            )
            attempt.last_active_at = now
        return WritingResponse(
            writing_task_id=writing_task_id,
            content=content,
            word_count=word_count,
            saved_at=now,
        )

    async def submit(self, attempt_id: uuid.UUID) -> AttemptResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            await self._synchronize_state(attempt, now)
            if attempt.status == AttemptStatus.PAUSED:
                raise AppError(
                    "ATTEMPT_PAUSED",
                    "Resume this attempt before submitting it.",
                    409,
                )
            if attempt.status == AttemptStatus.IN_PROGRESS:
                await self._score(attempt)
                self._finalize(
                    attempt,
                    status=AttemptStatus.SUBMITTED,
                    reason=FinishedReason.USER_SUBMIT,
                    now=now,
                )
                self.session.add(
                    AttemptEvent(
                        attempt_id=attempt.id,
                        event_type=EventType.SUBMITTED,
                        event_metadata={},
                        created_at=now,
                    )
                )
            response = self._to_response(attempt, now)
        return response

    async def review(self, attempt_id: uuid.UUID) -> AttemptReview:
        attempt = await self._require(attempt_id)
        if attempt.status in {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED}:
            raise AppError(
                "ATTEMPT_NOT_FINALIZED", "Submit the attempt before reviewing answer keys.", 409
            )
        answer_rows = [
            self._present_review_answer(answer)
            for answer in sorted(attempt.answers, key=lambda item: item.question.number)
        ]
        writing_rows: list[WritingReview] = []
        if attempt.module_type == ModuleType.WRITING:
            module = next(
                (
                    item
                    for item in attempt.test_version.modules
                    if item.module_type == ModuleType.WRITING
                ),
                None,
            )
            responses = {
                response.writing_task_id: response for response in attempt.writing_responses
            }
            scores = {score.writing_task_id: score for score in attempt.writing_scores}
            if module is not None:
                writing_rows = [
                    self._present_writing_review(
                        task,
                        responses.get(task.id),
                        scores.get(task.id),
                    )
                    for task in sorted(module.writing_tasks, key=lambda item: item.order_index)
                ]
        return AttemptReview(
            attempt=self._to_response(attempt),
            test_title=attempt.test_version.test.title,
            answers=answer_rows,
            writing_responses=writing_rows,
            highlights=[
                HighlightResponse.model_validate(item, from_attributes=True).model_dump(mode="json")
                for item in attempt.highlights
            ],
            flags=[
                {"question_id": str(item.question_id), "flagged": item.flagged}
                for item in attempt.flags
            ],
        )

    @staticmethod
    def _present_writing_review(
        task: WritingTask,
        response: AttemptWritingResponse | None,
        score: AttemptWritingScore | None,
    ) -> WritingReview:
        return WritingReview(
            writing_task_id=task.id,
            task_number=task.task_number,
            prompt=task.prompt,
            image_asset_id=task.image_asset_id,
            image_asset=(
                AssetResponse.model_validate(task.image_asset, from_attributes=True)
                if task.image_asset
                else None
            ),
            minimum_recommended_words=task.minimum_recommended_words,
            recommended_duration_seconds=task.recommended_duration_seconds,
            content=response.content if response else "",
            word_count=response.word_count if response else 0,
            score=(AttemptService._present_writing_score(score) if score else None),
        )

    @staticmethod
    def _present_writing_score(score: AttemptWritingScore) -> WritingTaskScore:
        overall = calculate_task_overall(score.ta, score.cc, score.lr, score.gra)
        return WritingTaskScore(
            ta=float(score.ta),
            cc=float(score.cc),
            lr=float(score.lr),
            gra=float(score.gra),
            overall=float(overall),
        )

    async def writing_review(self, attempt_id: uuid.UUID) -> WritingAttemptReview:
        review = await self.review(attempt_id)
        if review.attempt.module != ModuleType.WRITING:
            raise AppError(
                "WRITING_ATTEMPT_REQUIRED",
                "Writing review is only available for a Writing attempt.",
                422,
            )
        return self._present_writing_attempt_review(review)

    @staticmethod
    def _present_writing_attempt_review(review: AttemptReview) -> WritingAttemptReview:
        task_scores = {
            task.task_number: Decimal(str(task.score.overall))
            for task in review.writing_responses
            if task.score is not None
        }
        task_one_overall = task_scores.get(1)
        task_two_overall = task_scores.get(2)
        weighted_overall = calculate_weighted_writing_overall(task_one_overall, task_two_overall)
        return WritingAttemptReview(
            review=review,
            tasks=review.writing_responses,
            task1_overall=(float(task_one_overall) if task_one_overall is not None else None),
            task2_overall=(float(task_two_overall) if task_two_overall is not None else None),
            weighted_overall=(float(weighted_overall) if weighted_overall is not None else None),
            band_score=review.attempt.band_score,
        )

    async def grade_writing_task(
        self,
        attempt_id: uuid.UUID,
        writing_task_id: uuid.UUID,
        body: WritingTaskScoreUpdate,
    ) -> WritingAttemptReview:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            if attempt.module_type != ModuleType.WRITING:
                raise AppError(
                    "WRITING_ATTEMPT_REQUIRED",
                    "Writing criteria can only be saved on a Writing attempt.",
                    422,
                )
            now = TimerService.now()
            await self._synchronize_state(attempt, now)
            if attempt.status in {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED}:
                raise AppError(
                    "ATTEMPT_NOT_FINALIZED",
                    "Submit the Writing attempt before assigning a band.",
                    409,
                )
            module = next(
                (
                    item
                    for item in attempt.test_version.modules
                    if item.module_type == ModuleType.WRITING
                ),
                None,
            )
            task = (
                next(
                    (item for item in module.writing_tasks if item.id == writing_task_id),
                    None,
                )
                if module
                else None
            )
            if task is None:
                raise AppError(
                    "INVALID_WRITING_TASK",
                    "The Writing task does not belong to this attempt.",
                    422,
                )
            score = next(
                (
                    item
                    for item in attempt.writing_scores
                    if item.writing_task_id == writing_task_id
                ),
                None,
            )
            if score is None:
                score = AttemptWritingScore(
                    writing_task=task,
                    ta=body.ta,
                    cc=body.cc,
                    lr=body.lr,
                    gra=body.gra,
                )
                attempt.writing_scores.append(score)
            else:
                score.ta = body.ta
                score.cc = body.cc
                score.lr = body.lr
                score.gra = body.gra
            await self.session.flush()

            scores_by_task_id = {item.writing_task_id: item for item in attempt.writing_scores}
            task_overalls: dict[int, Decimal] = {}
            for candidate in module.writing_tasks:
                candidate_score = scores_by_task_id.get(candidate.id)
                if candidate_score and candidate.task_number in {1, 2}:
                    task_overalls[candidate.task_number] = calculate_task_overall(
                        candidate_score.ta,
                        candidate_score.cc,
                        candidate_score.lr,
                        candidate_score.gra,
                    )
            weighted_overall = calculate_weighted_writing_overall(
                task_overalls.get(1), task_overalls.get(2)
            )
            attempt.raw_score = None
            attempt.max_score = None
            attempt.band_score = calculate_final_writing_band(weighted_overall)
            response = self._present_writing_attempt_review(await self.review(attempt_id))
        return response

    @staticmethod
    def _present_review_answer(answer: AttemptAnswer) -> ReviewAnswer:
        question = answer.question
        group = question.question_group
        passage_blocks = (
            normalize_passage_blocks(group.passage.content_json, group.passage.id)
            if group.passage
            else []
        )
        normalized_group_config, normalized_questions = normalize_question_group_payload(
            question_type=group.question_type,
            group_config=group.config,
            questions=[
                {
                    "id": question.id,
                    "number": question.number,
                    "prompt": question.prompt,
                    "config": question.config,
                    "answer_key": question.answer_key,
                    "explanation": question.explanation,
                    "order_index": question.order_index,
                }
            ],
            group_id=group.id,
            passage_blocks=passage_blocks,
        )
        normalized_question = normalized_questions[0]
        normalized_value = normalize_response_value(
            question_type=group.question_type,
            value=answer.value,
            raw_group_config=group.config,
            raw_question_config=question.config,
            normalized_group_config=normalized_group_config,
            normalized_question_config=normalized_question["config"],
        )
        return ReviewAnswer(
            question_id=answer.question_id,
            question_number=normalized_question["number"],
            prompt=normalized_question["prompt"],
            value=normalized_value,
            answer_key=normalized_question["answer_key"],
            is_correct=answer.is_correct,
            explanation=normalized_question["explanation"],
        )

    async def history(self) -> AttemptList:
        attempts = await self.repository.list_history()
        history_now = TimerService.now()
        items: list[HistoryItem] = []
        for item in attempts:
            timer = TimerService.snapshot(
                mode=item.timer_mode,
                started_at=item.started_at,
                limit_seconds=item.timer_limit_seconds,
                paused_at=item.paused_at,
                total_paused_seconds=item.total_paused_seconds,
                now=item.finished_at or history_now,
            )
            items.append(
                HistoryItem(
                    attempt_id=item.id,
                    test_id=item.test_version.test_id,
                    test_version_id=item.test_version_id,
                    test_title=item.test_version.test.title,
                    version_number=item.test_version.version_number,
                    module=item.module_type,
                    status=item.status,
                    started_at=item.started_at,
                    finished_at=item.finished_at,
                    elapsed_seconds=(
                        item.elapsed_seconds
                        if item.elapsed_seconds is not None
                        else timer.elapsed_seconds
                    ),
                    timer_mode=item.timer_mode,
                    timer_limit_seconds=item.timer_limit_seconds,
                    remaining_seconds=timer.remaining_seconds,
                    raw_score=item.raw_score,
                    max_score=item.max_score,
                    band_score=item.band_score,
                )
            )
        items_by_id = {item.attempt_id: item for item in items}
        by_version: dict[uuid.UUID, list[Attempt]] = {}
        for attempt in attempts:
            by_version.setdefault(attempt.test_version_id, []).append(attempt)

        def latest_finalized(
            version_attempts: list[Attempt], module: ModuleType
        ) -> HistoryItem | None:
            candidates = [
                item
                for item in version_attempts
                if item.status not in {AttemptStatus.IN_PROGRESS, AttemptStatus.PAUSED}
                and item.module_type == module
            ]
            if not candidates:
                return None
            selected = max(
                candidates,
                key=lambda item: (
                    item.finished_at or item.started_at,
                    item.started_at,
                ),
            )
            return items_by_id[selected.id]

        groups: list[HistoryGroup] = []
        for version_attempts in by_version.values():
            version = version_attempts[0].test_version
            reading = latest_finalized(version_attempts, ModuleType.READING)
            listening = latest_finalized(version_attempts, ModuleType.LISTENING)
            writing = latest_finalized(version_attempts, ModuleType.WRITING)
            groups.append(
                HistoryGroup(
                    test_id=version.test_id,
                    test_version_id=version.id,
                    test_title=version.test.title,
                    version_number=version.version_number,
                    reading=reading,
                    listening=listening,
                    writing=writing,
                    overall_band_score=project_overall_band(
                        reading.band_score if reading else None,
                        listening.band_score if listening else None,
                        writing.band_score if writing else None,
                    ),
                )
            )
        group_recency = {
            version_id: max(item.started_at for item in version_attempts)
            for version_id, version_attempts in by_version.items()
        }
        groups.sort(key=lambda item: group_recency[item.test_version_id], reverse=True)
        return AttemptList(items=items, groups=groups, total=len(items))

    async def exam(self, attempt_id: uuid.UUID) -> AttemptExam:
        attempt_response = await self.get(attempt_id)
        attempt = await self._require(attempt_id)
        version = await TestRepository(self.session).get_version(attempt.test_version_id)
        assert version is not None
        answer_values = {item.question_id: item.value for item in attempt.answers}
        flags = {item.question_id: item.flagged for item in attempt.flags}
        module = next(
            (item for item in version.modules if item.module_type == attempt.module_type), None
        )
        passages: list[ExamPassage] = []
        listening_parts: list[ExamListeningPart] = []
        writing_tasks: list[ExamWritingTask] = []
        if module is not None:
            for passage in module.passages:
                passages.append(self._present_exam_passage(passage, answer_values, flags))
            for part in sorted(module.listening_parts, key=lambda item: item.order_index):
                listening_parts.append(
                    ExamListeningPart(
                        id=part.id,
                        title=part.title,
                        order_index=part.order_index,
                        question_groups=[
                            self._present_exam_group(group, answer_values, flags, [])
                            for group in sorted(
                                part.question_groups, key=lambda item: item.order_index
                            )
                        ],
                    )
                )
            responses = {
                response.writing_task_id: response for response in attempt.writing_responses
            }
            for task in sorted(module.writing_tasks, key=lambda item: item.order_index):
                response = responses.get(task.id)
                writing_tasks.append(
                    ExamWritingTask(
                        id=task.id,
                        task_number=task.task_number,
                        prompt=task.prompt,
                        image_asset_id=task.image_asset_id,
                        image_asset=(
                            AssetResponse.model_validate(task.image_asset, from_attributes=True)
                            if task.image_asset
                            else None
                        ),
                        minimum_recommended_words=task.minimum_recommended_words,
                        recommended_duration_seconds=task.recommended_duration_seconds,
                        order_index=task.order_index,
                        content=response.content if response else "",
                        word_count=response.word_count if response else 0,
                    )
                )
        return AttemptExam(
            attempt=attempt_response,
            test_title=version.test.title,
            passages=passages,
            highlights=[
                HighlightResponse.model_validate(item, from_attributes=True)
                for item in attempt.highlights
            ],
            listening_audio_asset=(
                AssetResponse.model_validate(module.audio_asset, from_attributes=True)
                if module and module.module_type == ModuleType.LISTENING and module.audio_asset
                else None
            ),
            listening_parts=listening_parts,
            writing_tasks=writing_tasks,
        )

    @staticmethod
    def _present_exam_passage(
        passage: ReadingPassage,
        answer_values: dict[uuid.UUID, Any],
        flags: dict[uuid.UUID, bool],
    ) -> ExamPassage:
        blocks = normalize_passage_blocks(passage.content_json, passage.id)
        exam_groups = [
            AttemptService._present_exam_group(group, answer_values, flags, blocks)
            for group in sorted(passage.question_groups, key=lambda item: item.order_index)
        ]
        return ExamPassage(
            id=passage.id,
            title=passage.title,
            order_index=passage.order_index,
            blocks=blocks,
            question_groups=exam_groups,
        )

    @staticmethod
    def _present_exam_group(
        group: QuestionGroup,
        answer_values: dict[uuid.UUID, Any],
        flags: dict[uuid.UUID, bool],
        passage_blocks: list[dict[str, Any]],
    ) -> ExamQuestionGroup:
        source_questions = sorted(group.questions, key=lambda item: item.order_index)
        question_rows = [
            {
                "id": question.id,
                "number": question.number,
                "prompt": question.prompt,
                "config": question.config,
                "answer_key": question.answer_key,
                "explanation": question.explanation,
                "order_index": question.order_index,
            }
            for question in source_questions
        ]
        normalized_config, normalized_questions = normalize_question_group_payload(
            question_type=group.question_type,
            group_config=group.config,
            questions=question_rows,
            group_id=group.id,
            passage_blocks=passage_blocks,
        )
        exam_questions: list[ExamQuestion] = []
        for source, question in zip(source_questions, normalized_questions, strict=True):
            stored_value = normalize_response_value(
                question_type=group.question_type,
                value=answer_values.get(source.id),
                raw_group_config=group.config,
                raw_question_config=source.config,
                normalized_group_config=normalized_config,
                normalized_question_config=question["config"],
            )
            exam_questions.append(
                ExamQuestion(
                    id=source.id,
                    number=question["number"],
                    prompt=question["prompt"],
                    config=question["config"],
                    order_index=question["order_index"],
                    value=stored_value,
                    flagged=flags.get(source.id, False),
                )
            )
        return ExamQuestionGroup(
            id=group.id,
            question_type=group.question_type,
            instruction=group.instruction,
            config={
                **normalized_config,
                **(
                    {
                        "image_asset": AssetResponse.model_validate(
                            group.image_asset, from_attributes=True
                        ).model_dump(mode="json")
                    }
                    if group.image_asset
                    else {}
                ),
            },
            order_index=group.order_index,
            questions=exam_questions,
        )

    async def reading_review(self, attempt_id: uuid.UUID) -> ReadingReview:
        review = await self.review(attempt_id)
        attempt = await self._require(attempt_id)
        version = await TestRepository(self.session).get_version(attempt.test_version_id)
        assert version is not None
        module = next(
            (item for item in version.modules if item.module_type == attempt.module_type), None
        )
        passages = (
            [ReadingService._present_passage(item) for item in module.passages] if module else []
        )
        return ReadingReview(
            review=review,
            passages=passages,
            highlights=[
                HighlightResponse.model_validate(item, from_attributes=True)
                for item in attempt.highlights
            ],
        )

    async def listening_review(self, attempt_id: uuid.UUID) -> ListeningReview:
        review = await self.review(attempt_id)
        attempt = await self._require(attempt_id)
        version = await TestRepository(self.session).get_version(attempt.test_version_id)
        assert version is not None
        module = next(
            (item for item in version.modules if item.module_type == attempt.module_type), None
        )
        parts = (
            [ReadingService._present_listening_part(item) for item in module.listening_parts]
            if module
            else []
        )
        return ListeningReview(
            review=review,
            audio_asset=(
                AssetResponse.model_validate(module.audio_asset, from_attributes=True)
                if module and module.audio_asset
                else None
            ),
            parts=parts,
        )

    async def save_flag(
        self, attempt_id: uuid.UUID, question_id: uuid.UUID, flagged: bool
    ) -> FlagResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            await self._ensure_mutable(attempt, now)
            await self._require_attempt_question(attempt, question_id)
            statement = insert(QuestionFlag).values(
                id=uuid.uuid4(),
                attempt_id=attempt.id,
                question_id=question_id,
                flagged=flagged,
                created_at=now,
                updated_at=now,
            )
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[QuestionFlag.attempt_id, QuestionFlag.question_id],
                    set_={"flagged": flagged, "updated_at": now},
                )
            )
            attempt.last_active_at = now
        return FlagResponse(question_id=question_id, flagged=flagged)

    async def create_highlight(
        self, attempt_id: uuid.UUID, body: HighlightCreate
    ) -> HighlightResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            await self._ensure_mutable(attempt, now)
            source_text = await self._highlight_source(attempt, body)
            self._validate_highlight_text(source_text, body)
            is_passage = body.target_kind == "PASSAGE_BLOCK"
            highlight = Highlight(
                attempt_id=attempt.id,
                target_kind=body.target_kind,
                target_id=body.target_id,
                segment_id=body.segment_id,
                passage_id=body.target_id if is_passage else None,
                start_block_id=body.segment_id if is_passage else None,
                start_offset=body.start_offset,
                end_block_id=body.segment_id if is_passage else None,
                end_offset=body.end_offset,
                selected_text=body.selected_text,
                created_at=now,
            )
            self.session.add(highlight)
            attempt.last_active_at = now
            await self.session.flush()
            response = HighlightResponse.model_validate(highlight, from_attributes=True)
        return response

    async def delete_highlight(self, attempt_id: uuid.UUID, highlight_id: uuid.UUID) -> None:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            await self._ensure_mutable(attempt, now)
            highlight = await self.session.scalar(
                select(Highlight).where(
                    Highlight.id == highlight_id, Highlight.attempt_id == attempt.id
                )
            )
            if highlight is None:
                raise AppError("HIGHLIGHT_NOT_FOUND", "The highlight does not exist.", 404)
            await self.session.delete(highlight)
            attempt.last_active_at = now

    async def delete_all_highlights(self, attempt_id: uuid.UUID) -> None:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            await self._ensure_mutable(attempt, now)
            await self.session.execute(delete(Highlight).where(Highlight.attempt_id == attempt.id))
            attempt.last_active_at = now

    async def delete_attempt(self, attempt_id: uuid.UUID) -> None:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            await self.session.delete(attempt)

    async def _require(self, attempt_id: uuid.UUID, *, for_update: bool = False) -> Attempt:
        attempt = await self.repository.get(attempt_id, for_update=for_update)
        if attempt is None:
            raise AppError("ATTEMPT_NOT_FOUND", "The requested attempt does not exist.", 404)
        return attempt

    async def _require_attempt_question(self, attempt: Attempt, question_id: uuid.UUID) -> Question:
        question = await self.session.scalar(
            select(Question)
            .join(QuestionGroup)
            .join(TestModule)
            .where(
                Question.id == question_id,
                TestModule.test_version_id == attempt.test_version_id,
                TestModule.module_type == attempt.module_type,
            )
        )
        if question is None:
            raise AppError("INVALID_QUESTION", "The question does not belong to this attempt.", 422)
        return question

    async def _highlight_source(self, attempt: Attempt, body: HighlightCreate) -> str:
        if body.target_kind == "PASSAGE_BLOCK":
            passage = await self.session.scalar(
                select(ReadingPassage)
                .join(TestModule)
                .where(
                    ReadingPassage.id == body.target_id,
                    TestModule.test_version_id == attempt.test_version_id,
                )
            )
            if passage is None:
                raise AppError(
                    "INVALID_HIGHLIGHT", "The passage does not belong to this attempt.", 422
                )
            blocks = {
                uuid.UUID(str(item["id"])): item["text"]
                for item in normalize_passage_blocks(passage.content_json, passage.id)
            }
            source = blocks.get(body.segment_id)
            if source is None:
                raise AppError(
                    "INVALID_HIGHLIGHT", "A referenced passage block does not exist.", 422
                )
            return source
        if body.target_kind == "QUESTION_PROMPT":
            question = await self._require_attempt_question(attempt, body.target_id)
            return question.prompt
        if body.target_kind == "TEXT_COMPLETION_SEGMENT":
            group = await self.session.scalar(
                select(QuestionGroup)
                .join(TestModule)
                .options(selectinload(QuestionGroup.questions))
                .where(
                    QuestionGroup.id == body.target_id,
                    QuestionGroup.question_type == "text_completion",
                    TestModule.test_version_id == attempt.test_version_id,
                    TestModule.module_type == attempt.module_type,
                )
            )
            if group is None:
                raise AppError(
                    "INVALID_HIGHLIGHT",
                    "The text completion group does not belong to this attempt.",
                    422,
                )
            normalized, _ = normalize_question_group_payload(
                question_type=group.question_type,
                group_config=group.config,
                questions=[
                    {
                        "id": item.id,
                        "number": item.number,
                        "prompt": item.prompt,
                        "config": item.config,
                        "answer_key": item.answer_key,
                        "order_index": item.order_index,
                    }
                    for item in group.questions
                ],
                group_id=group.id,
                passage_blocks=[],
            )
            for block in normalized.get("blocks", []):
                for segment in block.get("segments", []):
                    if segment.get("type") == "TEXT" and str(segment.get("id")) == str(
                        body.segment_id
                    ):
                        return str(segment.get("text") or "")
            raise AppError("INVALID_HIGHLIGHT", "The text segment does not exist.", 422)
        if body.target_kind == "QUESTION_GROUP_OPTION":
            group = await self.session.scalar(
                select(QuestionGroup)
                .join(TestModule)
                .options(selectinload(QuestionGroup.questions))
                .where(
                    QuestionGroup.id == body.target_id,
                    TestModule.test_version_id == attempt.test_version_id,
                    TestModule.module_type == attempt.module_type,
                )
            )
            if group is None:
                raise AppError(
                    "INVALID_HIGHLIGHT",
                    "The question group does not belong to this attempt.",
                    422,
                )
            passage_blocks: list[dict] = []
            if group.passage_id is not None:
                passage = await self.session.get(ReadingPassage, group.passage_id)
                if passage is not None:
                    passage_blocks = normalize_passage_blocks(passage.content_json, passage.id)
            normalized, _ = normalize_question_group_payload(
                question_type=group.question_type,
                group_config=group.config,
                questions=[
                    {
                        "id": item.id,
                        "number": item.number,
                        "prompt": item.prompt,
                        "config": item.config,
                        "answer_key": item.answer_key,
                        "order_index": item.order_index,
                    }
                    for item in group.questions
                ],
                group_id=group.id,
                passage_blocks=passage_blocks,
            )
            for option in normalized.get("options", []):
                if str(option.get("id")) == str(body.segment_id):
                    return str(option.get("text") or "")
            raise AppError("INVALID_HIGHLIGHT", "The question group option does not exist.", 422)
        raise AppError("INVALID_HIGHLIGHT", "The highlight target type is unsupported.", 422)

    @staticmethod
    def _validate_highlight_text(source_text: str, body: HighlightCreate) -> None:
        if body.start_offset >= body.end_offset or body.end_offset > len(source_text):
            raise AppError("INVALID_HIGHLIGHT", "Highlight offsets are invalid.", 422)
        actual = source_text[body.start_offset : body.end_offset]
        if " ".join(actual.split()) != " ".join(body.selected_text.split()):
            raise AppError(
                "INVALID_HIGHLIGHT", "Selected text does not match the source text.", 422
            )

    @staticmethod
    def _validate_highlight(passage: ReadingPassage, body: HighlightCreate) -> None:
        """Compatibility helper for validating legacy passage-only payloads."""
        blocks = {
            uuid.UUID(str(item["id"])): item["text"]
            for item in normalize_passage_blocks(passage.content_json, passage.id)
        }
        source = blocks.get(body.segment_id)
        if source is None:
            raise AppError("INVALID_HIGHLIGHT", "A referenced passage block does not exist.", 422)
        AttemptService._validate_highlight_text(source, body)

    async def _ensure_mutable(self, attempt: Attempt, now: datetime) -> None:
        await self._synchronize_state(attempt, now)
        if attempt.status == AttemptStatus.AUTO_SUBMITTED:
            raise AppError("ATTEMPT_EXPIRED", "The countdown period has ended.", 409)
        if attempt.status == AttemptStatus.PAUSED:
            raise AppError(
                "ATTEMPT_PAUSED",
                "Resume this attempt before changing it.",
                409,
            )
        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise AppError("ATTEMPT_FINALIZED", "This attempt no longer accepts changes.", 409)

    async def _synchronize_state(self, attempt: Attempt, now: datetime) -> None:
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return
        timer = TimerService.snapshot(
            mode=attempt.timer_mode,
            started_at=attempt.started_at,
            limit_seconds=attempt.timer_limit_seconds,
            paused_at=attempt.paused_at,
            total_paused_seconds=attempt.total_paused_seconds,
            now=now,
        )
        if timer.expired:
            await self._score(attempt)
            self._finalize(
                attempt,
                status=AttemptStatus.AUTO_SUBMITTED,
                reason=FinishedReason.TIME_EXPIRED,
                now=now,
            )
        elif TimerService.is_afk(attempt.last_active_at, now):
            await self._score(attempt)
            self._finalize(
                attempt,
                status=AttemptStatus.INTERRUPTED,
                reason=FinishedReason.AFK_TIMEOUT,
                now=now,
            )
            self.session.add(
                AttemptEvent(
                    attempt_id=attempt.id,
                    event_type=EventType.AFK_DETECTED,
                    event_metadata={},
                    created_at=now,
                )
            )

    @staticmethod
    def _finalize(
        attempt: Attempt,
        *,
        status: AttemptStatus,
        reason: FinishedReason,
        now: datetime,
    ) -> None:
        AttemptStateMachine.ensure_transition(attempt.status, status)
        attempt.status = status
        attempt.finished_reason = reason
        attempt.finished_at = now
        attempt.paused_at = None
        timer = TimerService.snapshot(
            mode=attempt.timer_mode,
            started_at=attempt.started_at,
            limit_seconds=attempt.timer_limit_seconds,
            total_paused_seconds=attempt.total_paused_seconds,
            now=now,
        )
        attempt.elapsed_seconds = timer.elapsed_seconds

    async def _score(self, attempt: Attempt) -> None:
        if attempt.module_type == ModuleType.WRITING:
            attempt.raw_score = None
            attempt.max_score = None
            attempt.band_score = None
            return
        questions = list(
            await self.session.scalars(
                select(Question)
                .join(QuestionGroup)
                .join(TestModule)
                .where(
                    TestModule.test_version_id == attempt.test_version_id,
                    TestModule.module_type == attempt.module_type,
                )
            )
        )
        if not questions:
            attempt.raw_score = None
            attempt.max_score = None
            attempt.band_score = None
            return
        attempt.max_score = len(questions)
        attempt.raw_score = int(
            await self.session.scalar(
                select(func.count(AttemptAnswer.id)).where(
                    AttemptAnswer.attempt_id == attempt.id,
                    AttemptAnswer.is_correct.is_(True),
                )
            )
            or 0
        )
        converter = (
            reading_raw_to_band
            if attempt.module_type == ModuleType.READING
            else listening_raw_to_band
        )
        band = converter(attempt.raw_score, attempt.max_score)
        attempt.band_score = Decimal(str(band)) if band is not None else None

    @staticmethod
    def _to_response(attempt: Attempt, now: datetime | None = None) -> AttemptResponse:
        snapshot_at = now or datetime.now(UTC)
        timer = TimerService.snapshot(
            mode=attempt.timer_mode,
            started_at=attempt.started_at,
            limit_seconds=attempt.timer_limit_seconds,
            paused_at=attempt.paused_at,
            total_paused_seconds=attempt.total_paused_seconds,
            now=attempt.finished_at or snapshot_at,
        )
        elapsed = (
            attempt.elapsed_seconds
            if attempt.elapsed_seconds is not None
            else timer.elapsed_seconds
        )
        return AttemptResponse(
            attempt_id=attempt.id,
            test_version_id=attempt.test_version_id,
            module=attempt.module_type,
            status=attempt.status,
            finished_reason=attempt.finished_reason,
            timer_mode=attempt.timer_mode,
            timer_limit_seconds=attempt.timer_limit_seconds,
            started_at=attempt.started_at,
            paused_at=attempt.paused_at,
            total_paused_seconds=attempt.total_paused_seconds,
            deadline_at=timer.deadline_at,
            last_active_at=attempt.last_active_at,
            finished_at=attempt.finished_at,
            elapsed_seconds=elapsed,
            remaining_seconds=timer.remaining_seconds,
            raw_score=attempt.raw_score,
            max_score=attempt.max_score,
            band_score=attempt.band_score,
            server_time=snapshot_at,
        )
