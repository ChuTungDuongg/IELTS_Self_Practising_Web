"""Resolve only observed evidence IDs into private, single-segment playback coordinates."""

from app.schemas.speaking_grading import CriterionFeedback, FeedbackComment
from app.schemas.speaking_timeline import resolve_audio_span


def resolve_feedback(criterion, evidence, feedback):
    index = {}
    for response in evidence.responses:
        feature = response.features
        if feature is None:
            continue
        records = (
            feature.fluency.events
            if criterion == "fc"
            else feature.pronunciation.observations
            if criterion == "pr"
            else []
        )
        for record in records:
            if record.evidence_id in index:
                raise ValueError("Ambiguous feedback evidence")
            if any(m.response_id != response.response_id for m in feature.timeline):
                raise ValueError("Feedback response provenance mismatch")
            index[record.evidence_id] = (response.response_id, feature.timeline, record)
    comments = []
    for comment in feedback.local_comments:
        if comment.scope == "OVERVIEW":
            if comment.evidence_ids:
                raise ValueError("Overview comments must not claim a unique location")
            comments.append(FeedbackComment(**comment.model_dump()))
            continue
        if not comment.evidence_ids or any(key not in index for key in comment.evidence_ids):
            raise ValueError("Unknown local feedback evidence")
        records = [index[key] for key in comment.evidence_ids]
        if len({row[0] for row in records}) != 1:
            raise ValueError("Feedback cannot cross responses")
        if any(row[2].start_ms is None or row[2].end_ms is None for row in records):
            raise ValueError("Feedback evidence has no location")
        start, end = min(row[2].start_ms for row in records), max(row[2].end_ms for row in records)
        span = resolve_audio_span(records[0][1], start, end)
        if span is None or end - start > 15000:
            raise ValueError("Feedback span is not replayable within one segment")
        comments.append(FeedbackComment(**comment.model_dump(), audio_span=span))
    return CriterionFeedback(**{**feedback.model_dump(), "local_comments": comments})


def unavailable_feedback(criterion, evidence):
    """Retain bounded, qualified observations even when coverage cannot support a band."""
    from app.schemas.speaking_grading import CriterionFeedbackInput

    comments = []
    for response in evidence.responses:
        feature = response.features
        if not feature or not feature.timeline:
            continue
        records = (
            feature.fluency.events if criterion == "fc" else feature.pronunciation.observations
        )
        for record in records:
            if criterion == "fc" and record.kind != "pause":
                continue
            if (
                record.start_ms is None
                or record.end_ms is None
                or record.end_ms - record.start_ms > 15000
            ):
                continue
            if not resolve_audio_span(feature.timeline, record.start_ms, record.end_ms):
                continue
            comments.append(
                {
                    "text": "A detected pause is available to replay; its cause is unknown."
                    if criterion == "fc"
                    else "The speech service supplied a pronunciation observation here; listen before treating it as an error.",
                    "scope": "LOCAL",
                    "evidence_ids": [record.evidence_id],
                }
            )
            break
        if len(comments) >= 3:
            break
    return resolve_feedback(
        criterion,
        evidence,
        CriterionFeedbackInput(
            feedback="Evidence coverage does not support a complete criterion band. Available observations remain advisory.",
            strengths=[],
            improvements=[],
            local_comments=comments,
        ),
    )
