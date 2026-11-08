"""Owner-only question annotation. Page reads and preflight never construct ASR."""

import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_segmentation import other_overlap, part_at
from app.models.speaking_benchmark import SpeakingBenchmarkReview as Review
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionJob as Job
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionRequest as Request
from app.schemas.speaking_benchmark import ReviewDraft
from app.schemas.speaking_benchmark_questions import (
    QUESTION_PROTOCOL,
    QuestionJobDTO,
    QuestionRequestDTO,
)
from app.schemas.speaking_benchmark_research import ProviderVariant
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark import check_revision, failure
from app.services.speaking_benchmark_research import provider_configuration
from app.services.speaking_benchmark_research import static_blockers as research_blockers
from app.services.speaking_benchmark_review import validate_draft

TERMINAL = {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}
MAX_ASSOCIATION_GAP_MS = 30000


def select_examiner_windows(result, draft, examiner, *, max_window_ms=60000, max_windows=100):
    """Regular diarization evidence is required: exclusivity is not voice separation."""
    validate_draft(result, draft)
    candidate = draft.candidate_speaker_id
    if (
        draft.roles.get(examiner) != "examiner"
        or not candidate
        or not draft.candidate_confirmed
        or draft.roles.get(candidate) != "candidate"
        or sum(r == "candidate" for r in draft.roles.values()) != 1
    ):
        raise failure("SPEAKING_QUESTIONS_SPEAKER_NOT_VERIFIED", 409)
    if not draft.boundaries_verified or not draft.part2_start_ms or not draft.part3_start_ms:
        raise failure("REPLAY_PART_BOUNDARIES_NOT_VERIFIED", 409)
    if any(s.included and s.speaker_id != candidate for s in draft.segments):
        raise failure("SPEAKING_QUESTIONS_CANDIDATE_WINDOWS_AMBIGUOUS", 409)
    boundaries = (draft.part2_start_ms, draft.part3_start_ms)
    windows, exclusions = [], []
    for turn in sorted(result.regular, key=lambda t: (t.start_ms, t.end_ms, t.id)):
        if turn.speaker_id != examiner:
            continue
        reasons = []
        if other_overlap(result, examiner, turn.start_ms, turn.end_ms):
            reasons.append("OTHER_SPEAKER_OVERLAP")
        if any(turn.start_ms < b < turn.end_ms for b in boundaries):
            reasons.append("PART_BOUNDARY_INSIDE_EXAMINER_TURN")
        if turn.end_ms - turn.start_ms > max_window_ms:
            reasons.append("EXAMINER_WINDOW_TOO_LONG")
        if reasons:
            exclusions.append({"turn_id": turn.id, "reasons": reasons})
        else:
            windows.append(
                turn.model_dump(mode="json")
                | {
                    "part_number": part_at(turn.start_ms, boundaries),
                }
            )
    if len(windows) > max_windows:
        raise failure("SPEAKING_QUESTIONS_WINDOW_LIMIT", 409)
    return windows, exclusions


def proposal_for_window(window, text, draft, provider_identity):
    text = text.strip()
    boundaries = (draft.part2_start_ms, draft.part3_start_ms)
    segments = sorted(
        [s for s in draft.segments if s.included and s.speaker_id == draft.candidate_speaker_id],
        key=lambda s: (s.start_ms, s.id),
    )
    following = [
        s
        for s in segments
        if s.start_ms >= window["end_ms"]
        and part_at(s.start_ms, boundaries) == window["part_number"]
    ]
    flags = []
    linked = following[0] if following else None
    if linked is None:
        flags.append("NO_FOLLOWING_CANDIDATE_RESPONSE")
    elif linked.start_ms - window["end_ms"] > MAX_ASSOCIATION_GAP_MS:
        flags.append("LONG_QUESTION_RESPONSE_GAP")
        linked = None
    if any(s.start_ms < window["start_ms"] < s.end_ms for s in segments):
        flags.append("EXAMINER_INTERRUPTION")
    lowered = text.casefold().strip(" .!?")
    if lowered in {"yes", "okay", "ok", "right", "thank you", "thanks", "i see", "all right"}:
        kind = "acknowledgement"
        flags.append("ACKNOWLEDGEMENT_REQUIRES_REVIEW")
    elif re.search(r"\b(repeat|say that again|what do you mean|clarify|pardon)\b", lowered):
        kind = "clarification"
        flags.append("CLARIFICATION_REQUIRES_REVIEW")
    elif "?" in text or re.match(
        r"^(who|what|when|where|why|how|do|does|did|is|are|have|has|can|could|would|will)\b",
        lowered,
    ):
        kind = "question"
    elif re.match(r"^(describe|tell me|talk about|please|you should|you have|now)\b", lowered):
        kind = "instruction"
        if window["part_number"] != 2:
            flags.append("INSTRUCTION_REQUIRES_REVIEW")
    else:
        kind = "unclear"
        flags.append("QUESTION_CLASSIFICATION_UNCERTAIN")
    if window["part_number"] == 2:
        flags.append("PART2_CUE_CARD_REQUIRES_MANUAL_ENTRY")
    if not text:
        flags.append("NO_RECOGNIZED_TEXT")
    return {
        "id": window["id"],
        "window_id": window["id"],
        "examiner_speaker_id": window["speaker_id"],
        "start_ms": window["start_ms"],
        "end_ms": window["end_ms"],
        "recognized_text": text,
        "provider_identity": provider_identity,
        "candidate_segment_id": linked.id if linked else None,
        "part_number": window["part_number"],
        "question_type": kind,
        "ambiguity_flags": flags,
        "human_verification_status": "PENDING",
    }


def build_proposals(job, draft, results):
    proposals = []
    for window in job.windows:
        result = results.get(window["id"])
        if result is None:
            continue
        p = proposal_for_window(window, result["lexical_transcript"], draft, result["provider"])
        p.update(
            source_review_revision=job.review_revision,
            source_sha256=job.source_sha256,
            draft_fingerprint=job.draft_fingerprint,
        )
        if result["status"] != "COMPLETE":
            p["ambiguity_flags"].append("RECOGNITION_INCOMPLETE")
        proposals.append(p)
    groups = {}
    for p in proposals:
        if p["candidate_segment_id"]:
            groups.setdefault(p["candidate_segment_id"], []).append(p)
    for group in groups.values():
        if len(group) > 1:
            for p in group:
                p["ambiguity_flags"].append("MULTIPLE_EXAMINER_UTTERANCES")
    return proposals


def question_configuration(settings, provider):
    return provider_configuration(
        settings, ProviderVariant(key="questions", provider=provider), "ASR_ONLY"
    )


def static_blockers(settings, config):
    reasons = [
        r
        for r in research_blockers(settings, config, "ASR_ONLY")
        if r != "SPEAKING_RESEARCH_LIVE_DISABLED"
    ]
    if not getattr(settings, "speaking_benchmark_questions_enabled", False) or not getattr(
        settings, "speaking_benchmark_questions_allow_live", False
    ):
        reasons.append("SPEAKING_QUESTIONS_LIVE_DISABLED")
    return sorted(set(reasons))


async def owned_job(service, sample_id, job_id, *, lock=False):
    await service.owned(sample_id, lock=lock)
    query = select(Job).where(
        Job.id == job_id, Job.sample_id == sample_id, Job.owner_id == service.owner_id
    )
    row = await service.session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
    return row


async def dto(session, row):
    value = QuestionJobDTO.model_validate(row)
    value.requests = [
        QuestionRequestDTO.model_validate(r)
        for r in await session.scalars(
            select(Request).where(Request.job_id == row.id).order_by(Request.created_at, Request.id)
        )
    ]
    return value


async def bound_input(service, job):
    sample = await service.owned(job.sample_id)
    accepted = [
        d["created_review_revision"] for d in job.decisions if d.get("created_review_revision")
    ]
    if sample.review_revision != (accepted[-1] if accepted else job.review_revision):
        raise failure("SPEAKING_QUESTIONS_REVIEW_CHANGED", 409)
    review, result = await service.review_row(sample, job.review_revision)
    draft = ReviewDraft.model_validate(review.draft)
    if (
        job.source_sha256 != sample.source_sha256
        or job.draft_fingerprint != fingerprint(review.draft)
        or job.model_fingerprint != fingerprint(result.identity)
    ):
        raise failure("SPEAKING_QUESTIONS_SOURCE_CHANGED", 409)
    try:
        windows, _ = select_examiner_windows(
            result,
            draft,
            job.examiner_speaker_id,
            max_window_ms=job.configuration["max_window_ms"],
            max_windows=job.configuration["max_windows"],
        )
    except BenchmarkInputError as error:
        raise failure(str(error), 409) from None
    if [w for w in windows if w["id"] in {x["id"] for x in job.windows}] != job.windows:
        raise failure("SPEAKING_QUESTIONS_SOURCE_CHANGED", 409)
    return sample, review, result, draft


async def create_job(service, sample_id, body):
    async with service.session.begin():
        sample = await service.owned(sample_id, lock=True)
        previous = await service.session.scalar(
            select(Job).where(
                Job.owner_id == service.owner_id, Job.submission_key == body.submission_key
            )
        )
        request_identity = fingerprint(
            [str(sample_id), body.model_dump(mode="json", exclude={"submission_key"})]
        )
        if previous:
            if previous.configuration["request_identity"] != request_identity:
                raise failure("SPEAKING_BENCHMARK_IDEMPOTENCY_CONFLICT", 409)
            return await dto(service.session, previous)
        check_revision(sample.review_revision, body.review_revision)
        review, result = await service.review_row(sample, body.review_revision)
        draft = ReviewDraft.model_validate(review.draft)
        try:
            windows, exclusions = select_examiner_windows(
                result,
                draft,
                body.examiner_speaker_id,
                max_window_ms=body.max_window_ms,
                max_windows=body.max_windows,
            )
        except BenchmarkInputError as error:
            raise failure(str(error), 409) from None
        if body.window_ids:
            windows = [w for w in windows if w["id"] in body.window_ids]
            if len(windows) != len(body.window_ids):
                raise failure("SPEAKING_QUESTIONS_WINDOW_MISMATCH", 409)
        duration = sum(w["end_ms"] - w["start_ms"] for w in windows)
        if not windows:
            raise failure("SPEAKING_QUESTIONS_NO_USABLE_EXAMINER_AUDIO", 409)
        if (
            duration > body.max_provider_audio_seconds * 1000
            or len(windows) > body.max_physical_requests
        ):
            raise failure("SPEAKING_QUESTIONS_BUDGET_EXCEEDED", 409)
        config = {
            "protocol": QUESTION_PROTOCOL,
            "request_identity": request_identity,
            "provider": question_configuration(service.settings, body.provider),
            "max_window_ms": body.max_window_ms,
            "max_windows": body.max_windows,
            "provider_audio_ms": duration,
            "requests": {body.provider: len(windows)},
            "limits": {
                "provider_audio_seconds": body.max_provider_audio_seconds,
                "physical_requests": body.max_physical_requests,
            },
        }
        identity = [
            str(sample.id),
            sample.source_sha256,
            fingerprint(review.draft),
            result.identity,
            body.examiner_speaker_id,
            windows,
            config,
        ]
        row = Job(
            sample_id=sample.id,
            owner_id=service.owner_id,
            submission_key=body.submission_key,
            review_revision=review.revision,
            source_sha256=sample.source_sha256,
            draft_fingerprint=fingerprint(review.draft),
            model_fingerprint=fingerprint(result.identity),
            examiner_speaker_id=body.examiner_speaker_id,
            configuration=config,
            fingerprint=fingerprint(identity),
            windows=windows,
            exclusions=exclusions,
        )
        service.session.add(row)
        await service.session.flush()
        return await dto(service.session, row)


async def preflight(service, sample_id, job_id):
    from app.services.speaking_benchmark_questions_audio import materialize_source

    async with service.session.begin():
        row = await owned_job(service, sample_id, job_id)
        sample, _, result, _ = await bound_input(service, row)
        config = row.configuration
        blockers = static_blockers(service.settings, config["provider"])
        if (
            question_configuration(service.settings, config["provider"]["provider"])
            != config["provider"]
        ):
            blockers.append("SPEAKING_QUESTIONS_CONFIGURATION_CHANGED")
        key, source_name, sha, duration = (
            sample.audio_key,
            result.source,
            sample.source_sha256,
            sample.duration_ms,
        )
        response = {
            "preflight_fingerprint": row.fingerprint,
            "can_start": not blockers,
            "blockers": sorted(set(blockers)),
            "windows": row.windows,
            "exclusions": row.exclusions,
            "requests": config["requests"],
            "provider_audio_seconds": config["provider_audio_ms"] / 1000,
            "limits": config["limits"],
            "warnings": [
                "HUMAN_QUESTION_VERIFICATION_REQUIRED",
                "DIARIZATION_DOES_NOT_SEPARATE_OVERLAPPING_VOICES",
                "ADMISSION_ESTIMATES_ARE_NOT_INVOICE_CAPS",
                "LIVE_ACCURACY_UNVERIFIED",
            ],
        }
    async with materialize_source(
        service.storage, key, source_name, sha, duration, service.settings
    ):
        pass
    return response


def check_consent(job, consent):
    provider = job.configuration["provider"]["provider"]
    if set(consent.estimates_usd) != {provider} or (
        provider != "faster_whisper_local" and consent.estimates_usd[provider] <= 0
    ):
        raise failure("SPEAKING_QUESTIONS_PROVIDER_ESTIMATES_REQUIRED", 409)
    if provider == "faster_whisper_modal" and not consent.modal_gpu:
        raise failure("SPEAKING_QUESTIONS_GPU_CONSENT_REQUIRED", 409)


async def start_job(service, sample_id, job_id, body):
    ready = await preflight(service, sample_id, job_id)
    if not ready["can_start"] or ready["preflight_fingerprint"] != body.preflight_fingerprint:
        raise failure("SPEAKING_QUESTIONS_PREFLIGHT_BLOCKED", 409)
    async with service.session.begin():
        row = await owned_job(service, sample_id, job_id, lock=True)
        await bound_input(service, row)
        check_consent(row, body.consent)
        if row.status != "DRAFT":
            raise failure("SPEAKING_QUESTIONS_ALREADY_STARTED", 409)
        row.consent = body.consent.model_dump(mode="json") | {
            "authorized_at": datetime.now(UTC).isoformat()
        }
        row.status, row.started_at = "PENDING", datetime.now(UTC)
        return await dto(service.session, row)


async def cancel_question_jobs(session, sample_id):
    """Caller owns the sample lock/transaction; fence requests before media deletion."""
    rows = list(
        await session.scalars(select(Job).where(Job.sample_id == sample_id).with_for_update())
    )
    active = False
    for row in rows:
        unknowns = list(
            await session.scalars(
                select(Request).where(
                    Request.job_id == row.id,
                    Request.status.in_(["ATTEMPTED", "INTERRUPTED_BILLING_UNKNOWN"]),
                )
            )
        )
        active |= row.status not in TERMINAL or bool(unknowns)
        if row.status not in TERMINAL:
            row.status, row.error_code, row.lease_token, row.lease_expires_at = (
                "CANCELLED",
                "SAMPLE_DELETED",
                None,
                None,
            )
            row.finished_at = datetime.now(UTC)
        for request in unknowns:
            if request.status == "ATTEMPTED":
                request.status = "INTERRUPTED_BILLING_UNKNOWN"
    await session.flush()
    return active


async def cancel_job(service, sample_id, job_id):
    async with service.session.begin():
        row = await owned_job(service, sample_id, job_id, lock=True)
        if row.status not in TERMINAL:
            row.status, row.lease_token, row.lease_expires_at = "CANCELLED", None, None
            row.finished_at = datetime.now(UTC)
            for request in await service.session.scalars(
                select(Request).where(Request.job_id == row.id, Request.status == "ATTEMPTED")
            ):
                request.status = "INTERRUPTED_BILLING_UNKNOWN"
        return await dto(service.session, row)


async def reconcile_job(service, sample_id, job_id, body):
    ready = await preflight(service, sample_id, job_id)
    if not ready["can_start"] or ready["preflight_fingerprint"] != body.preflight_fingerprint:
        raise failure("SPEAKING_QUESTIONS_PREFLIGHT_BLOCKED", 409)
    async with service.session.begin():
        row = await owned_job(service, sample_id, job_id, lock=True)
        await bound_input(service, row)
        check_consent(row, body.consent)
        request = await service.session.get(Request, body.request_id, with_for_update=True)
        if (
            not request
            or request.job_id != row.id
            or row.status != "INTERRUPTED"
            or (request.status != "INTERRUPTED_BILLING_UNKNOWN" or request.reconciliation)
        ):
            raise failure("SPEAKING_QUESTIONS_RECONCILIATION_MISMATCH", 409)
        request.reconciliation = {
            "owner_id": str(service.owner_id),
            "reason": body.reason,
            "authorized_at": datetime.now(UTC).isoformat(),
            "consent": body.consent.model_dump(mode="json"),
        }
        row.consent = body.consent.model_dump(mode="json") | {
            "authorized_at": datetime.now(UTC).isoformat(),
            "previous_authorizations": (row.consent or {}).get("previous_authorizations", [])
            + [{k: v for k, v in (row.consent or {}).items() if k != "previous_authorizations"}],
        }
        row.status, row.error_code = "PENDING", None
        return await dto(service.session, row)


def apply_decisions(job, draft, decisions, *, batch):
    """Only explicit acceptance changes prompts. Cue points and verified prompts survive."""
    updated = draft.model_copy(deep=True)
    proposals = {p["id"]: p for p in job.proposals}
    by_segment, records = {}, []
    boundaries = (draft.part2_start_ms, draft.part3_start_ms)
    for decision in decisions:
        proposal = proposals.get(decision.proposal_id)
        if not proposal:
            raise failure("SPEAKING_QUESTIONS_PROPOSAL_NOT_FOUND", 404)
        record = decision.model_dump(mode="json")
        if decision.action == "REJECT":
            records.append(record)
            continue
        ambiguous = bool(proposal["ambiguity_flags"])
        if ambiguous and (batch or not decision.ambiguity_reviewed):
            raise failure("SPEAKING_QUESTIONS_AMBIGUITY_REVIEW_REQUIRED", 409)
        segment_id = decision.candidate_segment_id or proposal["candidate_segment_id"]
        segment = next((s for s in updated.segments if s.id == segment_id and s.included), None)
        if not segment or segment.speaker_id != draft.candidate_speaker_id:
            raise failure("SPEAKING_QUESTIONS_CANDIDATE_ASSOCIATION_REQUIRED", 409)
        if segment.prompt_verified:
            raise failure("SPEAKING_QUESTIONS_VERIFIED_PROMPT_PRESERVED", 409)
        part = decision.part_number or proposal["part_number"]
        if part != part_at(segment.start_ms, boundaries):
            raise failure("SPEAKING_QUESTIONS_PART_ASSOCIATION_MISMATCH", 409)
        text = (decision.text if decision.text is not None else proposal["recognized_text"]).strip()
        if not text:
            raise failure("SPEAKING_QUESTIONS_TEXT_REQUIRED", 409)
        by_segment.setdefault(segment_id, []).append((proposal["start_ms"], text))
        record.update(text=text, candidate_segment_id=segment_id, part_number=part)
        records.append(record)
    for segment in updated.segments:
        if segment.id in by_segment:
            segment.prompt_text = "\n".join(t for _, t in sorted(by_segment[segment.id]))
            segment.prompt_verified = True
    return updated, records


async def decide(service, sample_id, job_id, body):
    async with service.session.begin():
        row = await owned_job(service, sample_id, job_id, lock=True)
        sample, _, _, _ = await bound_input(service, row)
        check_revision(sample.review_revision, body.expected_review_revision)
        check_revision(len(row.decisions), body.expected_decision_count)
        if row.status not in {"COMPLETED", "PARTIAL"}:
            raise failure("SPEAKING_QUESTIONS_NOT_FINALIZED", 409)
        previous, result = await service.review_row(sample)
        accepted_history = [d for d in row.decisions if d.get("created_review_revision")]
        expected = (
            accepted_history[-1]["draft_fingerprint"] if accepted_history else row.draft_fingerprint
        )
        if fingerprint(previous.draft) != expected:
            raise failure("SPEAKING_QUESTIONS_REVIEW_CHANGED", 409)
        draft, records = apply_decisions(
            row, ReviewDraft.model_validate(previous.draft), body.decisions, batch=body.batch
        )
        try:
            validate_draft(result, draft)
            draft = ReviewDraft.model_validate(draft.model_dump(mode="json"))
        except (BenchmarkInputError, ValueError) as error:
            raise failure(str(error), 409) from None
        accepted = any(d.action == "ACCEPT" for d in body.decisions)
        revision = None
        if accepted:
            revision = sample.review_revision + 1
            service.session.add(
                Review(
                    sample_id=sample.id,
                    revision=revision,
                    job_id=previous.job_id,
                    draft=draft.model_dump(mode="json"),
                )
            )
            sample.review_revision, sample.revision, sample.status = (
                revision,
                sample.revision + 1,
                "REVIEW",
            )
        stamp = datetime.now(UTC).isoformat()
        row.decisions = row.decisions + [
            r
            | {
                "id": str(uuid4()),
                "owner_id": str(service.owner_id),
                "decided_at": stamp,
                "created_review_revision": revision,
                "draft_fingerprint": fingerprint(draft.model_dump(mode="json")),
                "independently_reviewed": True,
            }
            for r in records
        ]
        await service.session.flush()
        return await dto(service.session, row)
