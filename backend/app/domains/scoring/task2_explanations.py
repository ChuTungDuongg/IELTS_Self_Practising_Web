"""Task 2 auxiliary evidence: local display bounds and item-local diagnostics."""

from dataclasses import dataclass, field

from pydantic import ValidationError

from app.domains.scoring.ai_writing_normalization import normalize_feedback
from app.domains.scoring.ai_writing_validation import safe_validation_issues
from app.domains.scoring.essay_sources import SourceSegment
from app.schemas.writing_ai import (
    EvidenceChoice,
    EvidenceSelection,
    RawTask2EvidenceChoice,
    RawTask2EvidenceSelection,
    ValidationIssue,
)


@dataclass
class ExplanationIssues:
    normalized: list[ValidationIssue] = field(default_factory=list)
    dropped: list[ValidationIssue] = field(default_factory=list)

    def drop(self, field: str, kind: str = "value_error") -> None:
        self.dropped.append(ValidationIssue(field=field, validation_type=kind))

    def invalid_item(self, prefix: str, error: ValidationError) -> None:
        self.dropped.extend(
            ValidationIssue(
                field=f"{prefix}.{issue.field}"[:120], validation_type=issue.validation_type
            )
            for issue in safe_validation_issues(error)
        )

    def bound(self, text: str, limit: int, field: str) -> str:
        if len(text.strip()) > limit:
            self.normalized.append(ValidationIssue(field=field, validation_type="string_too_long"))
        return normalize_feedback(text, limit)


def normalize_task2_evidence(
    raw: RawTask2EvidenceSelection, sources: dict[str, SourceSegment]
) -> tuple[EvidenceSelection, ExplanationIssues]:
    issues = ExplanationIssues()
    accepted = []
    if len(raw.evidence) > 4:
        issues.normalized.append(ValidationIssue(field="evidence", validation_type="too_long"))
    for index, value in enumerate(raw.evidence):
        if len(accepted) == 4:
            break
        prefix = f"evidence.{index}"
        try:
            item = RawTask2EvidenceChoice.model_validate(value)
        except ValidationError as error:
            issues.invalid_item(prefix, error)
            continue
        source = sources.get(item.source_id)
        if source is None or len(source.text) > 12000:
            issues.drop(f"{prefix}.source_id")
            continue
        assessment = issues.bound(item.assessment, 320, f"{prefix}.assessment")
        if not assessment:
            issues.drop(f"{prefix}.assessment", "string_too_short")
            continue
        if any(previous.source_id == item.source_id for previous in accepted):
            issues.drop(f"{prefix}.source_id")
            continue
        focus = issues.bound(item.focus, 160, f"{prefix}.focus") if item.focus is not None else None
        accepted.append(
            EvidenceChoice(source_id=item.source_id, assessment=assessment, focus=focus or None)
        )
    return EvidenceSelection(evidence=accepted), issues
