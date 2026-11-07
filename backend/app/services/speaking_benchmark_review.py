"""Web review projection over the existing provider-neutral replay policy."""

from app.evaluation.speaking.diarization_models import ResponseProposal
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_segment_review import approved_manifest
from app.evaluation.speaking.replay_segmentation import part_at, propose_responses
from app.schemas.speaking_benchmark import ReviewDraft, ReviewSegment
from app.services.speaking_audio import fingerprint


def initial_draft(result):
    return ReviewDraft(
        source_sha256=result.source_sha256,
        model_fingerprint=fingerprint(result.identity),
        roles={t.speaker_id: "unknown" for t in result.regular},
    )


def suggest_windows(result, draft):
    if draft.candidate_speaker_id not in {t.speaker_id for t in result.regular}:
        raise BenchmarkInputError("REPLAY_CANDIDATE_SPEAKER_UNKNOWN")
    boundaries = (
        (draft.part2_start_ms, draft.part3_start_ms)
        if draft.part2_start_ms and draft.part3_start_ms
        else None
    )
    proposals = propose_responses(
        result, candidate_speaker=draft.candidate_speaker_id, boundaries=boundaries
    )
    if len(proposals) > 100:
        raise BenchmarkInputError("REPLAY_TOO_MANY_RESPONSES_REVIEW_REQUIRED")
    return draft.model_copy(
        update={
            "segments": [
                ReviewSegment(
                    id=p.id, speaker_id=p.speaker_id, start_ms=p.start_ms, end_ms=p.end_ms
                )
                for p in proposals
            ]
        }
    )


def validate_draft(result, draft):
    if draft.source_sha256 != result.source_sha256 or draft.model_fingerprint != fingerprint(
        result.identity
    ):
        raise BenchmarkInputError("REPLAY_APPROVED_SOURCE_CHANGED")
    known = {t.speaker_id for t in result.regular}
    if set(draft.roles) != known or (
        draft.candidate_speaker_id is not None and draft.candidate_speaker_id not in known
    ):
        raise BenchmarkInputError("REPLAY_CANDIDATE_SPEAKER_UNKNOWN")
    if len({s.id for s in draft.segments}) != len(draft.segments) or any(
        s.speaker_id not in known or s.end_ms > result.duration_ms for s in draft.segments
    ):
        raise BenchmarkInputError("REPLAY_SEGMENT_RANGE_INVALID")
    if (
        draft.part2_start_ms is not None
        and draft.part3_start_ms is not None
        and not 0 < draft.part2_start_ms < draft.part3_start_ms < result.duration_ms
    ):
        raise BenchmarkInputError("REPLAY_PART_BOUNDARIES_INVALID")


def manifest_for_review(result, draft, max_response_ms):
    validate_draft(result, draft)
    candidate = draft.candidate_speaker_id
    if (
        not candidate
        or not draft.candidate_confirmed
        or draft.roles.get(candidate) != "candidate"
        or sum(r == "candidate" for r in draft.roles.values()) != 1
    ):
        raise BenchmarkInputError("REPLAY_SPEAKER_NOT_VERIFIED")
    if (
        not draft.boundaries_verified
        or draft.part2_start_ms is None
        or draft.part3_start_ms is None
    ):
        raise BenchmarkInputError("REPLAY_PART_BOUNDARIES_NOT_VERIFIED")
    boundaries = (draft.part2_start_ms, draft.part3_start_ms)
    selected = [s for s in draft.segments if s.included]
    if any(s.speaker_id != candidate for s in selected):
        raise BenchmarkInputError("REPLAY_AMBIGUOUS_OR_OVERLAPPING_SEGMENT")
    long_turns = [s.id for s in selected if s.long_turn and part_at(s.start_ms, boundaries) == 2]
    if len(long_turns) != 1 or sum(s.long_turn for s in selected) != 1:
        raise BenchmarkInputError("REPLAY_FULL_ATTEMPT_PARTS_REQUIRED")
    proposals = []
    for segment in selected:
        flags = []
        if any(segment.start_ms < b < segment.end_ms for b in boundaries):
            flags.append("PART_BOUNDARY_INSIDE_RESPONSE")
        support = sorted(
            [
                t
                for t in result.exclusive
                if t.speaker_id == candidate
                and t.start_ms < segment.end_ms
                and t.end_ms > segment.start_ms
            ],
            key=lambda t: t.start_ms,
        )
        if any(b.start_ms - a.end_ms > 3000 for a, b in zip(support, support[1:], strict=False)):
            flags.append("LONG_SILENCE_REVIEW")
        proposals.append(
            ResponseProposal(
                id=segment.id,
                source=result.source,
                speaker_id=segment.speaker_id,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                selected=True,
                part_number=part_at(segment.start_ms, boundaries),
                part_verified=True,
                prompt_text=segment.prompt_text,
                cue_points=segment.cue_points,
                prompt_verified=segment.prompt_verified,
                flags=flags,
            )
        )
    try:
        return approved_manifest(
            [result],
            proposals,
            roles_confirmed=True,
            acknowledged=[s.id for s in selected if s.silence_reviewed],
            max_response_ms=max_response_ms,
            long_turn_id=long_turns[0],
        )
    except BenchmarkInputError:
        raise
    except ValueError:
        raise BenchmarkInputError("REPLAY_SEGMENT_RANGE_INVALID") from None


def approval_errors(result, draft, max_response_ms):
    try:
        manifest_for_review(result, draft, max_response_ms)
        return []
    except BenchmarkInputError as error:
        return [str(error)]
