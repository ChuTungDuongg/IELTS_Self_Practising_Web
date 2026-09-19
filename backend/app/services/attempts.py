import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
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
from app.domains.timers import TimerService
from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptEvent,
    Highlight,
    Question,
    QuestionFlag,
    QuestionGroup,
    ReadingPassage,
    Test,
    TestModule,
    TestVersion,
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
    HistoryItem,
    ReviewAnswer,
    WritingReview,
)
from app.schemas.content import (
    AttemptExam,
    ExamListeningPart,
    ExamPassage,
    ExamQuestion,
    ExamQuestionGroup,
    FlagResponse,
    HighlightCreate,
    HighlightResponse,
    ListeningReview,
    ReadingReview,
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
            self._synchronize_state(attempt, TimerService.now())
            response = self._to_response(attempt)
        return response

    async def record_activity(self, attempt_id: uuid.UUID) -> AttemptResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            self._ensure_mutable(attempt, now)
            attempt.last_active_at = now
            response = self._to_response(attempt, now)
        return response

    async def save_answer(
        self, attempt_id: uuid.UUID, question_id: uuid.UUID, value: Any
    ) -> AnswerResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            self._ensure_mutable(attempt, now)
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

    async def submit(self, attempt_id: uuid.UUID) -> AttemptResponse:
        async with self.session.begin():
            attempt = await self._require(attempt_id, for_update=True)
            now = TimerService.now()
            self._synchronize_state(attempt, now)
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
        if attempt.status == AttemptStatus.IN_PROGRESS:
            raise AppError(
                "ATTEMPT_NOT_FINALIZED", "Submit the attempt before reviewing answer keys.", 409
            )
        answer_rows = [
            self._present_review_answer(answer)
            for answer in sorted(attempt.answers, key=lambda item: item.question.number)
        ]
        writing_rows = [
            WritingReview(
                writing_task_id=response.writing_task_id,
                task_number=response.writing_task.task_number,
                prompt=response.writing_task.prompt,
                content=response.content,
                word_count=response.word_count,
            )
            for response in attempt.writing_responses
        ]
        return AttemptReview(
            attempt=self._to_response(attempt),
            test_title=attempt.test_version.test.title,
            answers=answer_rows,
            writing_responses=writing_rows,
            highlights=[
                {
                    "id": str(item.id),
                    "passage_id": str(item.passage_id),
                    "start_block_id": str(item.start_block_id),
                    "start_offset": item.start_offset,
                    "end_block_id": str(item.end_block_id),
                    "end_offset": item.end_offset,
                    "selected_text": item.selected_text,
                }
                for item in attempt.highlights
            ],
            flags=[
                {"question_id": str(item.question_id), "flagged": item.flagged}
                for item in attempt.flags
            ],
        )

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
        items = [
            HistoryItem(
                attempt_id=item.id,
                test_title=item.test_version.test.title,
                version_number=item.test_version.version_number,
                module=item.module_type,
                status=item.status,
                started_at=item.started_at,
                finished_at=item.finished_at,
                elapsed_seconds=item.elapsed_seconds,
                raw_score=item.raw_score,
                max_score=item.max_score,
            )
            for item in attempts
        ]
        return AttemptList(items=items, total=len(items))

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
        return ReadingReview(review=review, passages=passages)

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
            self._ensure_mutable(attempt, now)
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
            self._ensure_mutable(attempt, now)
            passage = await self.session.scalar(
                select(ReadingPassage)
                .join(TestModule)
                .where(
                    ReadingPassage.id == body.passage_id,
                    TestModule.test_version_id == attempt.test_version_id,
                )
            )
            if passage is None:
                raise AppError(
                    "INVALID_PASSAGE", "The passage does not belong to this attempt.", 422
                )
            self._validate_highlight(passage, body)
            highlight = Highlight(
                attempt_id=attempt.id,
                passage_id=body.passage_id,
                start_block_id=body.start_block_id,
                start_offset=body.start_offset,
                end_block_id=body.end_block_id,
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
            self._ensure_mutable(attempt, now)
            highlight = await self.session.scalar(
                select(Highlight).where(
                    Highlight.id == highlight_id, Highlight.attempt_id == attempt.id
                )
            )
            if highlight is None:
                raise AppError("HIGHLIGHT_NOT_FOUND", "The highlight does not exist.", 404)
            await self.session.delete(highlight)
            attempt.last_active_at = now

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

    @staticmethod
    def _validate_highlight(passage: ReadingPassage, body: HighlightCreate) -> None:
        blocks = {
            uuid.UUID(str(item["id"])): item["text"]
            for item in normalize_passage_blocks(passage.content_json, passage.id)
        }
        start_text = blocks.get(body.start_block_id)
        end_text = blocks.get(body.end_block_id)
        if start_text is None or end_text is None:
            raise AppError("INVALID_HIGHLIGHT", "A referenced passage block does not exist.", 422)
        if body.start_block_id != body.end_block_id:
            raise AppError(
                "INVALID_HIGHLIGHT",
                "Multi-block highlights are reserved but not enabled in the Reading MVP.",
                422,
            )
        if body.start_offset >= body.end_offset or body.end_offset > len(start_text):
            raise AppError("INVALID_HIGHLIGHT", "Highlight offsets are invalid.", 422)
        actual = start_text[body.start_offset : body.end_offset]
        if " ".join(actual.split()) != " ".join(body.selected_text.split()):
            raise AppError("INVALID_HIGHLIGHT", "Selected text does not match the passage.", 422)

    def _ensure_mutable(self, attempt: Attempt, now: datetime) -> None:
        self._synchronize_state(attempt, now)
        if attempt.status == AttemptStatus.AUTO_SUBMITTED:
            raise AppError("ATTEMPT_EXPIRED", "The countdown period has ended.", 409)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise AppError("ATTEMPT_FINALIZED", "This attempt no longer accepts changes.", 409)

    def _synchronize_state(self, attempt: Attempt, now: datetime) -> None:
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return
        timer = TimerService.snapshot(
            mode=attempt.timer_mode,
            started_at=attempt.started_at,
            limit_seconds=attempt.timer_limit_seconds,
            now=now,
        )
        if timer.expired:
            self._finalize(
                attempt,
                status=AttemptStatus.AUTO_SUBMITTED,
                reason=FinishedReason.TIME_EXPIRED,
                now=now,
            )
        elif TimerService.is_afk(attempt.last_active_at, now):
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
        timer = TimerService.snapshot(
            mode=attempt.timer_mode,
            started_at=attempt.started_at,
            limit_seconds=attempt.timer_limit_seconds,
            now=now,
        )
        attempt.elapsed_seconds = timer.elapsed_seconds

    async def _score(self, attempt: Attempt) -> None:
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

    @staticmethod
    def _to_response(attempt: Attempt, now: datetime | None = None) -> AttemptResponse:
        snapshot_at = now or datetime.now(UTC)
        timer = TimerService.snapshot(
            mode=attempt.timer_mode,
            started_at=attempt.started_at,
            limit_seconds=attempt.timer_limit_seconds,
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
            deadline_at=timer.deadline_at,
            last_active_at=attempt.last_active_at,
            finished_at=attempt.finished_at,
            elapsed_seconds=elapsed,
            remaining_seconds=timer.remaining_seconds,
            raw_score=attempt.raw_score,
            max_score=attempt.max_score,
            server_time=snapshot_at,
        )
