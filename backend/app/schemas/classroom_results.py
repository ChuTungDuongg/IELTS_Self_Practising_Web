from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.attempts import AnswerResponse, AttemptResponse, AttemptReview, WritingReview
from app.schemas.content import ListeningReview, ReadingReview, WritingAttemptReview
from app.schemas.writing_ai import RunResponse


class AssignmentResultSummary(BaseModel):
    student_id: UUID
    student_display_name: str
    attempt: AttemptResponse
    session_id: UUID | None = None


class AssignmentResultDetail(AssignmentResultSummary):
    review: AttemptReview | None = None
    reading_review: ReadingReview | None = None
    listening_review: ListeningReview | None = None
    writing_review: WritingAttemptReview | None = None
    submitted_answers: list[AnswerResponse] = Field(default_factory=list)
    writing_responses: list[WritingReview] = Field(default_factory=list)
    ai_runs: list[RunResponse] = Field(default_factory=list)
