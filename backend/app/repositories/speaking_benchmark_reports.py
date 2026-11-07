"""Bounded owner-scoped read model. No provider imports or inference side effects."""

from sqlalchemy import or_, select

from app.models.speaking_benchmark import SpeakingBenchmarkHumanLabel as Label
from app.models.speaking_benchmark import SpeakingBenchmarkSample as Sample
from app.models.speaking_benchmark_grading import FINAL_STATUSES
from app.models.speaking_benchmark_grading import SpeakingBenchmarkGradingRun as Run
from app.services.speaking_benchmark import failure

FIELDS = ("fc", "lr", "gra", "pr", "overall")


async def report_inputs(session, owner_id, filters, maximum):
    scope = [Sample.owner_id == owner_id, Sample.deletion_pending_at.is_(None)]
    if filters.split:
        scope.append(Sample.split == filters.split)
    if filters.uploaded_from:
        scope.append(Sample.created_at >= filters.uploaded_from)
    if filters.uploaded_to:
        scope.append(Sample.created_at <= filters.uploaded_to)
    samples = list(
        await session.scalars(
            select(Sample)
            .where(*scope)
            .order_by(Sample.created_at.desc(), Sample.id)
            .limit(maximum + 1)
        )
    )
    if len(samples) > maximum:
        raise failure("SPEAKING_BENCHMARK_REPORT_LIMIT_NARROW_FILTERS", 422)
    ids = [s.id for s in samples]
    labels_query = select(Label).where(
        Label.sample_id.in_(ids), or_(*(getattr(Label, f).is_not(None) for f in FIELDS))
    )
    if filters.verified_only:
        labels_query = labels_query.where(Label.verified.is_(True))
    labels = list(
        await session.scalars(
            labels_query.distinct(Label.sample_id).order_by(
                Label.sample_id, Label.verified.desc(), Label.revision.desc()
            )
        )
    )
    runs_query = select(Run).where(
        Run.owner_id == owner_id, Run.sample_id.in_(ids), Run.status.in_(FINAL_STATUSES)
    )
    configs = list(
        await session.scalars(
            select(Run.config_fingerprint)
            .where(Run.owner_id == owner_id, Run.sample_id.in_(ids), Run.status.in_(FINAL_STATUSES))
            .distinct()
        )
    )
    selected = filters.configuration or (configs[0] if len(configs) == 1 else None)
    if selected:
        runs_query = runs_query.where(Run.config_fingerprint == selected)
    else:
        runs_query = runs_query.where(False)
    runs = list(
        await session.scalars(
            runs_query.distinct(Run.sample_id).order_by(
                Run.sample_id, Run.created_at.desc(), Run.id.desc()
            )
        )
    )
    # Speaker leakage is checked across both owner splits, not just displayed split.
    candidates = list(
        await session.execute(
            select(Sample.candidate_id, Sample.split)
            .where(
                Sample.owner_id == owner_id,
                Sample.deletion_pending_at.is_(None),
                Sample.candidate_id != "",
            )
            .distinct()
        )
    )
    return (
        samples,
        {r.sample_id: r for r in labels},
        {r.sample_id: r for r in runs},
        sorted(configs),
        selected,
        candidates,
    )
