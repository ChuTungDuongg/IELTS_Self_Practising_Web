"""Read-only dataset diagnosis and append-only, source-bound evaluation suites."""

import asyncio
import csv
import io
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.evaluation.speaking.runner import audio_digest
from app.models import User
from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingCheckpoint as Checkpoint
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.models.speaking_benchmark_quality import (
    SpeakingBenchmarkEvaluationSuite as Suite,
)
from app.models.speaking_benchmark_quality import (
    SpeakingBenchmarkHoldoutAudit as Audit,
)
from app.models.speaking_benchmark_quality import (
    SpeakingBenchmarkQualitySnapshot as Snapshot,
)
from app.models.speaking_benchmark_quality import (
    SpeakingBenchmarkRegressionGate as Gate,
)
from app.models.speaking_benchmark_quality import (
    SpeakingBenchmarkRegressionReport as Report,
)
from app.models.speaking_benchmark_questions import SpeakingBenchmarkQuestionJob as QuestionJob
from app.models.speaking_benchmark_questions import (
    SpeakingBenchmarkQuestionRequest as QuestionRequest,
)
from app.models.speaking_benchmark_research import SpeakingBenchmarkASRObservation as Observation
from app.models.speaking_benchmark_research import (
    SpeakingBenchmarkASRReference as Reference,
)
from app.models.speaking_benchmark_research import SpeakingBenchmarkExperimentVariant as Variant
from app.schemas.speaking_benchmark_quality import (
    QUALITY_PROTOCOL,
    GateCreate,
    GateDTO,
    GateEvaluate,
    GatePolicy,
    PersistedSelection,
    RegressionReportDTO,
    SuiteDTO,
)
from app.services.speaking_audio import fingerprint
from app.services.speaking_benchmark import check_revision, failure
from app.services.speaking_benchmark_audio import load_approved_input
from app.services.speaking_benchmark_gate_evidence import collect_persisted_evidence
from app.services.speaking_benchmark_human import bands, latest_assessments, resolve_human_label
from app.services.speaking_benchmark_quality_metrics import evaluate_regression
from app.services.speaking_benchmark_research_metrics import (
    reference_metrics,
)


def issue(issues, code, severity, artifact, identifier, remediation):
    issues.append(
        dict(
            code=code,
            severity=severity,
            artifact=artifact,
            artifact_id=str(identifier),
            remediation=remediation,
        )
    )


def source_digest(service, sample):
    with service.storage.materialize(
        sample.audio_key,
        max_bytes=service.settings.speaking_benchmark_max_upload_mb * 1024**2,
    ) as path:
        return audio_digest(path)


async def collect_quality(service, body):
    """Caller owns transaction. Observes current storage; never repairs artifacts."""
    issues, samples = [], []
    all_samples = list(
        await service.session.scalars(
            select(Sample).where(
                Sample.owner_id == service.owner_id,
                Sample.deletion_pending_at.is_(None),
            )
        )
    )
    splits = {}
    for sample in all_samples:
        if sample.candidate_id:
            splits.setdefault(sample.candidate_id, set()).add(sample.split)
    for selection in sorted(body.cohort, key=lambda c: str(c.sample_id)):
        sample = await service.owned(selection.sample_id)
        start = len(issues)
        frozen = dict(
            sample_id=str(sample.id),
            code=sample.code,
            candidate_id=sample.candidate_id,
            split=sample.split,
            source_sha256=sample.source_sha256,
            review_revision=selection.review_revision,
            manifest_fingerprint=None,
            label_fingerprint=None,
            reference_fingerprint=None,
            human={},
            windows=[],
            references=[],
        )
        try:
            _, review, manifest, _ = await load_approved_input(
                service, sample.id, selection.review_revision
            )
        except (AppError, ValueError, TypeError):
            issue(
                issues,
                "APPROVED_REVIEW_INVALID",
                "BLOCKED",
                "review",
                sample.id,
                "Save and approve a source-bound review after inspecting the recording.",
            )
            samples.append(frozen | {"eligible": False})
            continue
        frozen["manifest_fingerprint"] = review.fingerprint
        frozen["windows"] = [s.model_dump(mode="json") for s in manifest.segments]
        try:
            actual = await asyncio.to_thread(source_digest, service, sample)
            if actual != sample.source_sha256:
                issue(
                    issues,
                    "SOURCE_SHA_MISMATCH",
                    "BLOCKED",
                    "audio",
                    sample.id,
                    "Restore the original source asset; re-review a changed recording as a new sample.",
                )
        except (OSError, ValueError, RuntimeError):
            issue(
                issues,
                "SOURCE_ASSET_UNAVAILABLE",
                "BLOCKED",
                "audio",
                sample.id,
                "Restore the private source asset and rerun quality checks.",
            )
        if not sample.rights_confirmed:
            issue(
                issues,
                "RIGHTS_UNCONFIRMED",
                "BLOCKED",
                "sample",
                sample.id,
                "Confirm recording rights.",
            )
        if not sample.candidate_id:
            issue(
                issues,
                "CANDIDATE_ID_MISSING",
                "INSUFFICIENT_DATA",
                "sample",
                sample.id,
                "Set a consistent candidate pseudonym to count independent speakers.",
            )
        elif len(splits.get(sample.candidate_id, set())) > 1:
            issue(
                issues,
                "CANDIDATE_SPLIT_LEAKAGE",
                "BLOCKED",
                "sample",
                sample.id,
                "Resolve candidate overlap between DEV and HOLDOUT before evaluation.",
            )
        if body.policy.require_all_parts and {w["part_number"] for w in frozen["windows"]} != {
            1,
            2,
            3,
        }:
            issue(
                issues,
                "PART_COVERAGE_INCOMPLETE",
                "BLOCKED",
                "review",
                sample.id,
                "Review and include candidate responses for all three parts.",
            )
        if review.revision != sample.review_revision:
            issue(
                issues,
                "HISTORICAL_APPROVED_REVIEW",
                "NEEDS_REVIEW",
                "review",
                sample.id,
                "Confirm that this historical approved revision is intentional.",
            )
        label = await resolve_human_label(
            service.session,
            service.owner_id,
            sample.id,
            review.revision,
            body.label_selection.model_dump(mode="json"),
        )
        frozen["label"] = label
        frozen["label_fingerprint"] = label["fingerprint"]
        frozen["human"] = label["bands"] if label["eligible"] else {}
        ratings = await latest_assessments(
            service.session, service.owner_id, sample.id, review.revision
        )
        eligible_ratings = [
            bands(r)
            for r in ratings
            if r.independently_performed
            and r.provenance in {"internal_blind", "external_verified_report"}
        ]
        if any(
            len(values := [r.get(field) for r in eligible_ratings if r.get(field) is not None]) > 1
            and max(values) - min(values) > 0.5
            for field in ("fc", "lr", "gra", "pr", "overall")
        ):
            issue(
                issues,
                "RATER_DISAGREEMENT_REVIEW_REQUIRED",
                "NEEDS_REVIEW",
                "human_label",
                sample.id,
                "Review the independently submitted scores and record an explicit adjudication.",
            )
        if label["eligible"] and any(
            label["bands"].get(f) is None for f in ("fc", "lr", "gra", "pr", "overall")
        ):
            issue(
                issues,
                "HUMAN_CRITERION_MISSING",
                "NEEDS_REVIEW",
                "human_label",
                sample.id,
                "Keep missing criteria unavailable; collect a human score when assessable.",
            )
        if body.policy.require_human_label and not label["eligible"]:
            issue(
                issues,
                "HUMAN_LABEL_MISSING",
                "BLOCKED",
                "human_label",
                sample.id,
                "Collect an independent assessment or an owner adjudication for this approved review.",
            )
        if (
            label["id"]
            and body.policy.require_source_bound_labels
            and label["binding_status"] != "SOURCE_BOUND"
        ):
            issue(
                issues,
                "LEGACY_LABEL_UNBOUND",
                "BLOCKED",
                "human_label",
                sample.id,
                "Use an independent or adjudicated source-bound human label.",
            )
        if body.policy.require_adjudication and (
            label["kind"] != "ADJUDICATED" or not label["eligible"]
        ):
            issue(
                issues,
                "ADJUDICATION_REQUIRED",
                "BLOCKED",
                "human_label",
                sample.id,
                "Record an explicit owner human adjudication.",
            )
        for window in frozen["windows"]:
            ref = await service.session.scalar(
                select(Reference)
                .where(
                    Reference.owner_id == service.owner_id,
                    Reference.sample_id == sample.id,
                    Reference.review_revision == review.revision,
                    Reference.segment_id == window["id"],
                    Reference.status == "VERIFIED",
                )
                .order_by(Reference.revision.desc())
                .limit(1)
            )
            binding_ok = (
                ref
                and ref.source_sha256 == sample.source_sha256
                and ref.manifest_fingerprint == review.fingerprint
                and ref.start_ms == window["start_ms"]
                and ref.end_ms == window["end_ms"]
            )
            valid = (
                binding_ok
                and not ref.uncertainty
                and reference_metrics("", ref).get("truth") == "HUMAN_VERIFIED"
            )
            if not valid:
                issue(
                    issues,
                    "ASR_REFERENCE_UNAVAILABLE",
                    "BLOCKED" if body.policy.require_asr_references else "NEEDS_REVIEW",
                    "reference",
                    f"{sample.id}:{window['id']}",
                    "Verify a human transcript with valid annotations for this exact candidate window.",
                )
            frozen["references"].append(
                dict(
                    segment_id=window["id"],
                    id=str(ref.id) if ref else None,
                    revision=ref.revision if ref else None,
                    eligible=bool(valid),
                    source_sha256=ref.source_sha256 if ref else None,
                    manifest_fingerprint=ref.manifest_fingerprint if ref else None,
                    start_ms=ref.start_ms if ref else None,
                    end_ms=ref.end_ms if ref else None,
                    normalization=ref.normalization if ref else None,
                )
            )
        frozen["reference_fingerprint"] = fingerprint(frozen["references"])
        runs = list(
            await service.session.scalars(
                select(Run).where(
                    Run.owner_id == service.owner_id,
                    Run.sample_id == sample.id,
                    Run.review_revision == review.revision,
                )
            )
        )
        variants = list(
            await service.session.scalars(
                select(Variant).where(
                    Variant.owner_id == service.owner_id,
                    Variant.sample_id == sample.id,
                    Variant.review_revision == review.revision,
                )
            )
        )
        question_jobs = list(
            await service.session.scalars(
                select(QuestionJob).where(
                    QuestionJob.owner_id == service.owner_id, QuestionJob.sample_id == sample.id
                )
            )
        )
        requests = list(
            await service.session.scalars(
                select(Checkpoint).where(Checkpoint.run_id.in_([r.id for r in runs]))
            )
        )
        requests += list(
            await service.session.scalars(
                select(Observation).where(Observation.variant_id.in_([r.id for r in variants]))
            )
        )
        requests += list(
            await service.session.scalars(
                select(QuestionRequest).where(
                    QuestionRequest.job_id.in_([r.id for r in question_jobs])
                )
            )
        )
        frozen["experiment_diagnostics"] = dict(
            run_ids=[str(r.id) for r in runs],
            variant_ids=[str(v.id) for v in variants],
            request_ids=[str(r.id) for r in requests],
        )
        for request in requests:
            if request.reused_from is None and request.status in {
                "ATTEMPTED",
                "INTERRUPTED_BILLING_UNKNOWN",
            }:
                issue(
                    issues,
                    "BILLING_RECONCILIATION_REQUIRED",
                    "BLOCKED",
                    "request",
                    request.id,
                    "Resolve the exact physical attempt before further evaluation.",
                )
            elif request.status == "FAILED":
                issue(
                    issues,
                    "PROVIDER_RESULT_INCOMPLETE",
                    "NEEDS_REVIEW",
                    "request",
                    request.id,
                    "Inspect the persisted provider failure; missing results remain unavailable.",
                )
        for variant in variants:
            if (
                variant.status in {"COMPLETED", "PARTIAL"}
                and not variant.grading_run_id
                and sum(
                    r.status == "COMPLETED"
                    for r in requests
                    if getattr(r, "variant_id", None) == variant.id
                )
                < len(variant.windows)
            ):
                issue(
                    issues,
                    "ASR_OBSERVATIONS_MISSING",
                    "NEEDS_REVIEW",
                    "variant",
                    variant.id,
                    "Inspect missing candidate windows before comparing provider coverage.",
                )
        for run in runs:
            if run.prediction and any(
                run.prediction.get("bands", {}).get(field) is None
                for field in ("fc", "lr", "gra", "pr", "overall")
            ):
                issue(
                    issues,
                    "PREDICTED_CRITERION_MISSING",
                    "NEEDS_REVIEW",
                    "grading_run",
                    run.id,
                    "Keep unassessable criteria unavailable in the evaluation denominator.",
                )
        frozen["eligible"] = not any(i["severity"] == "BLOCKED" for i in issues[start:])
        samples.append(frozen)
    independent = len(
        {s["candidate_id"] for s in samples if s["candidate_id"] and s.get("eligible")}
    )
    if independent < body.policy.minimum_independent_candidates:
        issue(
            issues,
            "INSUFFICIENT_INDEPENDENT_CANDIDATES",
            "INSUFFICIENT_DATA",
            "cohort",
            "selection",
            "Collect more distinct, verified candidate pseudonyms; repeated recordings do not add independence.",
        )
    levels = {i["severity"] for i in issues}
    status = next(
        (s for s in ("BLOCKED", "NEEDS_REVIEW", "INSUFFICIENT_DATA") if s in levels),
        "READY",
    )
    evidence = dict(
        protocol=QUALITY_PROTOCOL,
        status=status,
        issues=issues,
        samples=samples,
        issue_counts=dict(Counter(i["code"] for i in issues)),
        eligible_samples=sum(s.get("eligible", False) for s in samples),
        ineligible_samples=sum(not s.get("eligible", False) for s in samples),
        independent_candidates=independent,
    )
    return evidence | dict(
        evaluated_at=datetime.now(UTC).isoformat(), fingerprint=fingerprint(evidence)
    )


async def quality_report(service, body):
    async with service.session.begin():
        return await collect_quality(service, body)


def snapshot_dto(row):
    return {
        k: getattr(row, k)
        for k in (
            "id",
            "protocol",
            "configuration",
            "fingerprint",
            "status",
            "report",
            "created_at",
        )
    }


async def create_snapshot(service, body):
    async with service.session.begin():
        report = await collect_quality(service, body)
        row = Snapshot(
            owner_id=service.owner_id,
            protocol=QUALITY_PROTOCOL,
            configuration=body.model_dump(mode="json"),
            fingerprint=report["fingerprint"],
            status=report["status"],
            report=report,
        )
        service.session.add(row)
        await service.session.flush()
        return snapshot_dto(row)


async def owned_artifact(service, model, identifier):
    row = await service.session.scalar(
        select(model).where(model.id == identifier, model.owner_id == service.owner_id)
    )
    if row is None:
        raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
    return row


def require_holdout(suite, consent):
    holdout = any(s["split"] == "HOLDOUT" for s in suite.configuration["samples"])
    if holdout and not consent:
        raise failure("SPEAKING_SUITE_HOLDOUT_CONSENT_REQUIRED", 409)
    return holdout


def audit_holdout(service, suite, action, details=None):
    service.session.add(
        Audit(
            owner_id=service.owner_id,
            suite_id=suite.id,
            actor_id=service.owner_id,
            action=action,
            details=details or {},
        )
    )


async def create_suite(service, body):
    async with service.session.begin():
        await service.session.get(User, service.owner_id, with_for_update=True)
        family = body.family_id or uuid4()
        latest = (
            await service.session.scalar(
                select(func.max(Suite.revision)).where(
                    Suite.owner_id == service.owner_id, Suite.family_id == family
                )
            )
            or 0
        )
        check_revision(latest, body.expected_revision)
        if body.family_id and not latest:
            raise failure("SPEAKING_BENCHMARK_NOT_FOUND", 404)
        report = await collect_quality(service, body)
        config = dict(
            protocol=QUALITY_PROTOCOL,
            label_selection=body.label_selection.model_dump(mode="json"),
            policy=body.policy.model_dump(mode="json"),
            samples=report["samples"],
            quality=report,
        )
        row = Suite(
            owner_id=service.owner_id,
            family_id=family,
            revision=latest + 1,
            name=body.name,
            description=body.description,
            configuration=config,
            fingerprint=fingerprint(config),
            frozen_at=datetime.now(UTC),
        )
        holdout = require_holdout(row, body.holdout_evaluation)
        service.session.add(row)
        await service.session.flush()
        if holdout:
            audit_holdout(service, row, "SUITE_FROZEN")
        return SuiteDTO.model_validate(row)


async def get_suite(service, identifier, consent=False):
    async with service.session.begin():
        row = await owned_artifact(service, Suite, identifier)
        if require_holdout(row, consent):
            audit_holdout(service, row, "SUITE_INSPECTED")
        return SuiteDTO.model_validate(row)


async def list_artifacts(service, model, offset=0, limit=25):
    async with service.session.begin():
        rows = list(
            await service.session.scalars(
                select(model)
                .where(model.owner_id == service.owner_id)
                .order_by(model.created_at.desc(), model.id)
                .offset(offset)
                .limit(limit)
            )
        )
        # Lists disclose identity and aggregate readiness only; HOLDOUT membership is protected.
        if model == Suite:
            return [
                dict(
                    id=r.id,
                    family_id=r.family_id,
                    revision=r.revision,
                    name=r.name,
                    description=r.description,
                    configuration={
                        "holdout": any(s["split"] == "HOLDOUT" for s in r.configuration["samples"]),
                        "sample_count": len(r.configuration["samples"]),
                    },
                    fingerprint=r.fingerprint,
                    frozen_at=r.frozen_at,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        return [snapshot_dto(r) for r in rows]


async def suite_audits(service, identifier):
    async with service.session.begin():
        await owned_artifact(service, Suite, identifier)
        return [
            dict(
                id=r.id,
                actor_id=r.actor_id,
                action=r.action,
                details=r.details,
                created_at=r.created_at,
            )
            for r in await service.session.scalars(
                select(Audit)
                .where(Audit.suite_id == identifier, Audit.owner_id == service.owner_id)
                .order_by(Audit.created_at, Audit.id)
            )
        ]


async def create_gate(service, body: GateCreate) -> GateDTO:
    async with service.session.begin():
        suite = await owned_artifact(service, Suite, body.suite_id)
        config = dict(
            suite_id=str(body.suite_id),
            baseline=body.baseline.model_dump(mode="json"),
            candidate=body.candidate.model_dump(mode="json"),
            policy=body.policy.model_dump(mode="json"),
        )
        row = Gate(
            owner_id=service.owner_id,
            suite_id=suite.id,
            name=body.name,
            baseline=body.baseline.model_dump(mode="json"),
            candidate=body.candidate.model_dump(mode="json"),
            policy=body.policy.model_dump(mode="json"),
            fingerprint=fingerprint(config),
        )
        service.session.add(row)
        await service.session.flush()
        return GateDTO.model_validate(row)


async def get_gate(service, identifier: UUID) -> GateDTO:
    async with service.session.begin():
        row = await owned_artifact(service, Gate, identifier)
        return GateDTO.model_validate(row)


async def list_gates(service, offset: int = 0, limit: int = 25) -> list[GateDTO]:
    async with service.session.begin():
        rows = list(
            await service.session.scalars(
                select(Gate)
                .where(Gate.owner_id == service.owner_id)
                .order_by(Gate.created_at.desc(), Gate.id)
                .offset(offset)
                .limit(limit)
            )
        )
        return [GateDTO.model_validate(r) for r in rows]


async def evaluate_gate(service, identifier: UUID, body: GateEvaluate) -> RegressionReportDTO:
    async with service.session.begin():
        gate = await owned_artifact(service, Gate, identifier)
        suite = await owned_artifact(service, Suite, gate.suite_id)
        holdout = require_holdout(suite, body.holdout_evaluation)
        baseline_evidence = await collect_persisted_evidence(
            service, suite, PersistedSelection.model_validate(gate.baseline)
        )
        candidate_evidence = await collect_persisted_evidence(
            service, suite, PersistedSelection.model_validate(gate.candidate)
        )
        quality = suite.configuration.get("quality", {})
        policy = GatePolicy.model_validate(gate.policy)
        report = evaluate_regression(
            policy, suite.configuration, baseline_evidence, candidate_evidence, quality
        )
        report.update(
            suite_id=str(suite.id),
            suite_fingerprint=suite.fingerprint,
            gate_fingerprint=gate.fingerprint,
            policy=gate.policy,
            baseline_evidence=baseline_evidence,
            candidate_evidence=candidate_evidence,
        )
        rep_fingerprint = fingerprint(dict(gate_id=str(gate.id), report=report))
        row = Report(
            owner_id=service.owner_id,
            gate_id=gate.id,
            status=report["status"],
            protocol=report["protocol"],
            fingerprint=rep_fingerprint,
            report=report,
        )
        service.session.add(row)
        await service.session.flush()
        if holdout:
            audit_holdout(
                service,
                suite,
                "GATE_EVALUATED",
                {"gate_id": str(gate.id), "report_id": str(row.id)},
            )
        return RegressionReportDTO.model_validate(row)


async def list_gate_reports(
    service, gate_id: UUID, offset: int = 0, limit: int = 25
) -> list[RegressionReportDTO]:
    async with service.session.begin():
        await owned_artifact(service, Gate, gate_id)
        rows = list(
            await service.session.scalars(
                select(Report)
                .where(Report.owner_id == service.owner_id, Report.gate_id == gate_id)
                .order_by(Report.created_at.desc(), Report.id)
                .offset(offset)
                .limit(limit)
            )
        )
        return [RegressionReportDTO.model_validate(r) for r in rows]


async def get_report(service, identifier: UUID) -> tuple[RegressionReportDTO, dict]:
    async with service.session.begin():
        row = await owned_artifact(service, Report, identifier)
        gate = await owned_artifact(service, Gate, row.gate_id)
        suite = await owned_artifact(service, Suite, gate.suite_id)
        if any(s["split"] == "HOLDOUT" for s in suite.configuration["samples"]):
            audit_holdout(service, suite, "REPORT_INSPECTED", {"report_id": str(row.id)})
        return RegressionReportDTO.model_validate(row), row.report


def export_report_csv(report_data: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "metric",
            "direction",
            "status",
            "baseline",
            "candidate",
            "difference",
            "relative_difference",
            "tolerable_regression",
            "baseline_coverage",
            "candidate_coverage",
            "ci95_lower",
            "ci95_upper",
        ]
    )
    for m in report_data.get("metrics", []):
        ci = (m.get("paired") or {}).get("ci95") or [None, None]
        writer.writerow(
            [
                m.get("metric"),
                m.get("direction"),
                m.get("status"),
                m.get("baseline"),
                m.get("candidate"),
                m.get("difference"),
                m.get("relative_difference"),
                m.get("tolerable_regression"),
                m.get("baseline_coverage"),
                m.get("candidate_coverage"),
                ci[0],
                ci[1],
            ]
        )
    return output.getvalue()
