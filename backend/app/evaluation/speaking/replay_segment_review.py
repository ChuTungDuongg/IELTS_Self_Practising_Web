"""Explicit operator review. Machine drafts can never set candidate_only_verified."""

from typing import Literal

from pydantic import Field

from app.evaluation.speaking.diarization_models import DiarizationResult, ProposalBundle
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_audio import probe_audio, resolve_source
from app.evaluation.speaking.replay_cache import read_checkpoint, save_checkpoint
from app.evaluation.speaking.replay_models import ReplayManifest, ReplaySegment, read_json
from app.evaluation.speaking.replay_segmentation import (
    other_overlap,
    part_at,
    propose_responses,
    suggest_roles,
)
from app.evaluation.speaking.runner import audio_digest
from app.schemas.speaking_grading import StrictDTO
from app.services.speaking_audio import fingerprint


class QuestionContext(StrictDTO):
    prompt_text: str = Field(min_length=1, max_length=10000)
    cue_points: list[str] = Field(default_factory=list, max_length=20)
    source_kind: Literal["operator", "human_transcript", "local_asr"] = "operator"
    verified: bool = False


class ReviewState(StrictDTO):
    schema_version: Literal[1] = 1
    identity: str
    candidate_speakers: dict[str, str] = Field(default_factory=dict)
    part_boundaries: dict[str, tuple[int, int]] = Field(default_factory=dict)
    file_parts: dict[str, Literal[1, 2, 3]] = Field(default_factory=dict)
    questions: dict[str, QuestionContext] = Field(default_factory=dict)
    edits: dict[str, tuple[int, int]] = Field(default_factory=dict)
    excluded: list[str] = Field(default_factory=list)
    acknowledged: list[str] = Field(default_factory=list)


def load_diarization(root):
    path = root / "diarization.json"
    data = read_checkpoint(path)
    if not data:
        raise BenchmarkInputError("REPLAY_DIARIZATION_DRAFT_MISSING_RUN_AUTO_SEGMENT")
    results = [DiarizationResult.model_validate(item) for item in data["sources"]]
    if not results or len({r.source for r in results}) != len(results):
        raise BenchmarkInputError("REPLAY_DIARIZATION_DRAFT_INVALID")
    for result in results:
        if audio_digest(resolve_source(root, result.source)) != result.source_sha256:
            raise BenchmarkInputError("REPLAY_DIARIZATION_SOURCE_CHANGED_RERUN_AUTO_SEGMENT")
    return data, results


def load_state(root, identity):
    existing = read_checkpoint(root / "segments.review.json")
    if existing and existing.get("identity") == identity:
        return ReviewState.model_validate(existing)
    if existing:
        save_checkpoint(root / f"SENSITIVE-review-{fingerprint(existing)[:20]}.json", existing)
    return ReviewState(identity=identity)


def generate_proposals(root, *, state=None):
    data, results = load_diarization(root)
    state = state or load_state(root, data["identity"])
    roles, segments = {}, []
    if state.candidate_speakers.keys() - {r.source for r in results}:
        raise BenchmarkInputError("REPLAY_CANDIDATE_SPEAKER_UNKNOWN")
    for result in results:
        roles[result.source] = suggest_roles(result)
        speaker = state.candidate_speakers.get(result.source)
        if speaker is not None and speaker not in roles[result.source]:
            raise BenchmarkInputError("REPLAY_CANDIDATE_SPEAKER_UNKNOWN")
        for identifier, role in roles[result.source].items():
            role["candidate_confirmed"] = identifier == speaker
        proposals = propose_responses(
            result,
            candidate_speaker=speaker,
            boundaries=state.part_boundaries.get(result.source),
            file_part=state.file_parts.get(result.source),
            pause_tolerance_ms=data["pause_tolerance_ms"],
        )
        for proposal in proposals:
            if proposal.id in state.edits:
                start, end = state.edits[proposal.id]
                if not 0 <= start < end <= result.duration_ms:
                    raise BenchmarkInputError("REPLAY_SEGMENT_RANGE_INVALID")
                proposal.start_ms, proposal.end_ms = start, end
                proposal.part_number = state.file_parts.get(result.source) or part_at(
                    start, state.part_boundaries.get(result.source)
                )
                proposal.part_verified = proposal.part_number is not None
                proposal.flags = [
                    f
                    for f in proposal.flags
                    if f not in {"OTHER_SPEAKER_OVERLAP", "PART_BOUNDARY_INSIDE_RESPONSE"}
                ]
                if other_overlap(result, proposal.speaker_id, start, end):
                    proposal.flags.append("OTHER_SPEAKER_OVERLAP")
                if any(
                    start < boundary < end
                    for boundary in state.part_boundaries.get(result.source, ())
                ):
                    proposal.flags.append("PART_BOUNDARY_INSIDE_RESPONSE")
                    proposal.part_number, proposal.part_verified = None, False
            if proposal.id in state.excluded:
                proposal.selected = False
            question = state.questions.get(proposal.id)
            if question:
                proposal.prompt_text, proposal.cue_points = (
                    question.prompt_text,
                    question.cue_points,
                )
                proposal.prompt_verified = question.verified
            segments.append(proposal)
    bundle = ProposalBundle(
        identity=data["identity"],
        sources={r.source: r.source_sha256 for r in results},
        roles=roles,
        segments=segments,
        role_verification="confirmed"
        if all(r.source in state.candidate_speakers for r in results)
        else "pending",
        limitations=[
            "MODEL_IDENTITY_AND_BOUNDARIES_UNVERIFIED",
            "NO_AUTOMATIC_PART_OR_QUESTION_TRUTH",
        ],
    )
    save_checkpoint(root / "segments.proposed.json", bundle.model_dump(mode="json"))
    save_checkpoint(root / "segments.review.json", state.model_dump(mode="json"))
    template = root / "question-context.template.json"
    save_checkpoint(
        template,
        {
            "schema_version": 1,
            "questions": {
                p.id: {
                    "prompt_text": p.prompt_text,
                    "cue_points": p.cue_points,
                    "source_kind": "operator",
                    "verified": p.prompt_verified,
                }
                for p in segments
                if p.selected
            },
        },
    )
    return bundle


def review_summary(root):
    bundle = generate_proposals(root)
    data, results = load_diarization(root)
    state = load_state(root, data["identity"])
    from app.evaluation.speaking.diarization_review_html import write_local_review

    write_local_review(root, results, bundle, part_boundaries=state.part_boundaries)
    from app.evaluation.speaking.diarization_evaluation import evaluate_segmentation

    evaluation = evaluate_segmentation(root, results, bundle, state)
    save_checkpoint(root / "diarization-evaluation.json", {"schema_version": 1, **evaluation})
    lines = [
        "LOCAL REVIEW ONLY: no Azure/OpenAI calls.",
        f"Role verification: {bundle.role_verification}; boundary/content verification: pending.",
    ]
    for result in results:
        for speaker, role in bundle.roles[result.source].items():
            examples = [
                (t.start_ms, t.end_ms) for t in result.exclusive if t.speaker_id == speaker
            ][:3]
            confirmed = state.candidate_speakers.get(result.source) == speaker
            lines.append(
                f"{speaker}: {role['exclusive_speech_ms']}ms; suggested={role['suggested_role']}; "
                f"candidate_confirmed={confirmed}; examples_ms={examples}"
            )
    for proposal in bundle.segments:
        lines.append(
            f"{proposal.id}: {proposal.speaker_id} {proposal.start_ms}..{proposal.end_ms}ms; "
            f"selected={proposal.selected}; Part={proposal.part_number}; prompt_verified={proposal.prompt_verified}; "
            f"context_turns={proposal.context_turn_ids}; flags={','.join(proposal.flags)}"
        )
    lines.append(
        "Review original audio locally. Confirm identity, Part transitions and real questions; resolve overlaps, then --approve-segments."
    )
    lines.append(
        "Optional local audio timeline: review.local.html (open on this computer, no server or upload)."
    )
    return "\n".join(lines)


def update_review(
    root,
    *,
    candidate=None,
    part_boundaries=None,
    file_parts=False,
    questions=None,
    edit=None,
    exclude=(),
    acknowledge=(),
):
    data, results = load_diarization(root)
    state = load_state(root, data["identity"])
    if candidate:
        matches = [r for r in results if candidate in {t.speaker_id for t in r.regular}]
        if len(matches) != 1:
            raise BenchmarkInputError("REPLAY_CANDIDATE_SPEAKER_UNKNOWN_OR_FILE_AMBIGUOUS")
        state.candidate_speakers[matches[0].source] = candidate
    if part_boundaries is not None:
        if (
            len(results) != 1
            or not 0 < part_boundaries[0] < part_boundaries[1] < results[0].duration_ms
        ):
            raise BenchmarkInputError("REPLAY_PART_BOUNDARIES_INVALID")
        state.part_boundaries[results[0].source] = tuple(part_boundaries)
    if file_parts:
        from pathlib import Path

        mapping = {r.source: Path(r.source).stem.lower() for r in results}
        if set(mapping.values()) != {"part1", "part2", "part3"}:
            raise BenchmarkInputError("REPLAY_PART_FILES_REQUIRED")
        state.file_parts = {name: int(stem[-1]) for name, stem in mapping.items()}
    bundle = generate_proposals(root, state=state)
    known = {p.id for p in bundle.segments}
    if questions:
        # Explicit private context import; no automatic local/cloud ASR.
        path = questions.resolve()
        if not path.is_relative_to(root.resolve()):
            raise BenchmarkInputError("REPLAY_PRIVATE_ROOT_REQUIRED")
        raw = read_checkpoint(path)
        incoming = {
            key: QuestionContext.model_validate(value) for key, value in raw["questions"].items()
        }
        if incoming.keys() - known:
            raise BenchmarkInputError("REPLAY_QUESTION_SEGMENT_UNKNOWN")
        state.questions.update(incoming)
    if edit:
        identifier, start, end = edit
        if identifier not in known:
            raise BenchmarkInputError("REPLAY_SEGMENT_UNKNOWN")
        state.edits[identifier] = (int(start), int(end))
    if set(exclude) - known or set(acknowledge) - known:
        raise BenchmarkInputError("REPLAY_SEGMENT_UNKNOWN")
    state.excluded = sorted(set(state.excluded) | set(exclude))
    state.acknowledged = sorted(set(state.acknowledged) | set(acknowledge))
    return generate_proposals(root, state=state)


def approve_segments(root, settings):
    bundle = generate_proposals(root)
    data, results = load_diarization(root)
    state = load_state(root, data["identity"])
    if bundle.role_verification != "confirmed":
        raise BenchmarkInputError("REPLAY_SPEAKER_NOT_VERIFIED")
    selected = [p for p in bundle.segments if p.selected]
    if not selected:
        raise BenchmarkInputError("REPLAY_NO_CANDIDATE_RESPONSES")
    for proposal in selected:
        result = next(r for r in results if r.source == proposal.source)
        if not any(
            t.speaker_id == proposal.speaker_id
            and t.start_ms < proposal.end_ms
            and t.end_ms > proposal.start_ms
            for t in result.regular
        ):
            raise BenchmarkInputError("REPLAY_SEGMENT_OUTSIDE_CANDIDATE_SUPPORT")
        if any(
            f in proposal.flags for f in ("OTHER_SPEAKER_OVERLAP", "PART_BOUNDARY_INSIDE_RESPONSE")
        ):
            raise BenchmarkInputError("REPLAY_AMBIGUOUS_OR_OVERLAPPING_SEGMENT")
        if "LONG_SILENCE_REVIEW" in proposal.flags and proposal.id not in state.acknowledged:
            raise BenchmarkInputError("REPLAY_LONG_SILENCE_REVIEW_REQUIRED")
        if not proposal.part_verified or proposal.part_number is None:
            raise BenchmarkInputError("REPLAY_PART_BOUNDARIES_NOT_VERIFIED")
        if not proposal.prompt_verified or not proposal.prompt_text.strip():
            raise BenchmarkInputError("REPLAY_PROMPT_CONTEXT_REQUIRED")
        if proposal.end_ms - proposal.start_ms > settings.speaking_max_decoded_seconds * 1000:
            raise BenchmarkInputError("REPLAY_RESPONSE_DURATION_EXCEEDED")
    sources = {r.source: r.source_sha256 for r in results}
    for name, checksum in sources.items():
        if probe_audio(resolve_source(root, name), settings)["sha256"] != checksum:
            raise BenchmarkInputError("REPLAY_DIARIZATION_SOURCE_CHANGED_RERUN_AUTO_SEGMENT")
    part2 = [p for p in selected if p.part_number == 2]
    long_turn = max(part2, key=lambda p: p.end_ms - p.start_ms).id if part2 else None
    manifest = ReplayManifest(
        candidate_only_verified=True,
        segments=[
            ReplaySegment(
                id=p.id,
                source=p.source,
                part_number=p.part_number,
                start_ms=p.start_ms,
                end_ms=p.end_ms,
                prompt_type="LONG_TURN"
                if p.id == long_turn
                else "FOLLOW_UP"
                if p.part_number == 3
                else "SHORT_ANSWER",
                prompt_text=p.prompt_text,
                cue_points=p.cue_points,
                speaker_role="candidate",
                speaker_id="candidate-1",
            )
            for p in selected
        ],
    )
    if manifest.grading_limitations():
        raise BenchmarkInputError("REPLAY_" + manifest.grading_limitations()[0])
    existing = root / "segments.json"
    if existing.exists():
        old = read_json(existing, ReplayManifest)
        if old.candidate_only_verified:
            save_checkpoint(
                root / f"SENSITIVE-approved-{fingerprint(old.model_dump(mode='json'))[:20]}.json",
                old.model_dump(mode="json"),
            )
    save_checkpoint(existing, manifest.model_dump(mode="json"))
    save_checkpoint(
        root / "segments.approval.json",
        {
            "schema_version": 1,
            "identity": bundle.identity,
            "manifest_hash": fingerprint(manifest.model_dump(mode="json")),
            "sources": sources,
            "candidate_speakers": state.candidate_speakers,
            "operator_action": "approve-segments",
            "identity_verified": True,
            "boundaries_and_candidate_content_verified": True,
            "parts_verified": True,
            "prompts_verified": True,
            "same_candidate_across_sources_verified": True,
        },
    )
    return manifest


def verify_approval(root, manifest, metadata):
    receipt = read_checkpoint(root / "segments.approval.json")
    if receipt is None:
        return  # Existing hand-authored ReplayManifest remains the authoritative manual workflow.
    if (
        receipt.get("operator_action") != "approve-segments"
        or receipt.get("manifest_hash") != fingerprint(manifest.model_dump(mode="json"))
        or any(
            not receipt.get(key)
            for key in (
                "identity_verified",
                "boundaries_and_candidate_content_verified",
                "parts_verified",
                "prompts_verified",
                "same_candidate_across_sources_verified",
            )
        )
    ):
        raise BenchmarkInputError("REPLAY_APPROVAL_CHANGED_REVIEW_REQUIRED")
    if any(
        name not in metadata or metadata[name]["sha256"] != checksum
        for name, checksum in receipt["sources"].items()
    ):
        raise BenchmarkInputError("REPLAY_APPROVED_SOURCE_CHANGED")
