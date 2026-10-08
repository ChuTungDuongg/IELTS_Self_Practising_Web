import json

import pytest
from test_tacs_tree import snapshot
from test_task1_benchmark import benchmark_files as benchmark_files
from test_task1_tacs import HybridProvider

from app.core.config import Settings
from app.evaluation.task1.anchor_sources import (
    AnchorSource,
    guard_leakage,
    load_anchor_manifest,
    load_postgres_anchors,
    normalized_essay_hash,
)
from app.evaluation.task1.architectures import architecture_configurations
from app.evaluation.task1.manifest import BenchmarkInputError, load_manifest
from app.evaluation.task1.models import EvaluationRecord
from app.evaluation.task1.report import aggregate
from app.evaluation.task1.runner import run_benchmark


def test_normalization_and_split_leakage(benchmark_files):
    path, sample = benchmark_files
    items = load_manifest(path, "dev")
    source = AnchorSource(snapshot(), frozenset({sample["id"]}))
    with pytest.raises(BenchmarkInputError, match="BENCHMARK_ANCHOR_LEAKAGE"):
        guard_leakage(items, source)
    assert normalized_essay_hash(" Ａ  word\n\nVALUE ") == normalized_essay_hash("a word value")
    bank = snapshot()
    changed = bank.model_copy(
        update={
            "anchors": (
                bank.anchors[0].model_copy(update={"response_text": sample["essay"].upper()}),
            )
        }
    )
    with pytest.raises(BenchmarkInputError, match="BENCHMARK_ANCHOR_LEAKAGE"):
        guard_leakage(items, AnchorSource(changed))


@pytest.mark.asyncio
async def test_all_architectures_and_independent_self_consistency(benchmark_files, tmp_path):
    path, sample = benchmark_files
    # Fictional chart truth differs from this fake provider; perception is not certified OK.
    items = load_manifest(path, "dev")
    source = AnchorSource(snapshot())
    configs = architecture_configurations(Settings(_env_file=None), "all", "off", source=source)
    providers = []

    def factory(config):
        provider = HybridProvider()
        providers.append(provider)
        return provider

    report = await run_benchmark(
        items, configs, tmp_path / "report", provider_factory=factory, anchor_source=source
    )
    assert len(providers) == 6  # A0 + A1 + three independent A0 repeats + A3
    records = [EvaluationRecord.model_validate(r) for r in report["records"]]
    assert {r.architecture for r in records} == {
        "direct",
        "mts",
        "direct-self-consistency",
        "anchor-pairwise",
    }
    repeated = next(r for r in records if r.architecture == "direct-self-consistency")
    assert len(repeated.repeats) == 3 and repeated.predicted["gra"] == 7
    assert not repeated.perception["reconciled"]["perception_ok"]
    hybrid = next(r for r in records if r.architecture == "anchor-pairwise")
    assert hybrid.scoring_diagnostics["criteria"]["ta"]["mode"] == "GROUNDED_DIRECT"
    assert sum(p.pairwise_calls for p in providers) == 6
    metrics = report["configurations"][hybrid.config_key]["tacs"]
    assert metrics["language_criterion_count"] == 3
    assert metrics["pairwise_calls"] == 6 and metrics["nodes"]["mean"] == 1
    assert metrics["directional_agreement_rate"] == 1
    assert metrics["direct_fallback_count"] == 0
    reasons = (
        "NO_ANCHORS",
        "INSUFFICIENT_CONTIGUOUS_COVERAGE",
        "OUT_OF_RANGE",
        "POSITION_CONFLICT",
        "BUDGET_EXHAUSTED",
        "PAIRWISE_PROVIDER_FAILURE",
    )
    fallback_records = [
        hybrid.model_copy(
            update={
                "scoring_diagnostics": {
                    "criteria": {
                        "ta": {"mode": "GROUNDED_DIRECT"},
                        **{
                            t: {
                                "mode": "DIRECT_FALLBACK",
                                "fallback_reason": reason,
                                "pairwise_calls": 2,
                                "tree": {
                                    "nodes": [
                                        {
                                            "band": 7,
                                            "forward": "TARGET_BETTER",
                                            "reverse": "ANCHOR_BETTER",
                                        }
                                    ]
                                },
                            }
                            for t in ("cc", "lr", "gra")
                        },
                    }
                }
            }
        )
        for reason in reasons
    ]
    fallback_metrics = aggregate(fallback_records)["tacs"]
    assert (
        fallback_metrics["language_criterion_count"]
        == fallback_metrics["direct_fallback_count"]
        == 18
    )
    assert fallback_metrics["directional_agreement_rate"] == 0
    assert all(
        v["count"] == 3 and v["rate"] == 1 / 6
        for v in fallback_metrics["fallback_reasons"].values()
    )
    public = json.dumps(report)
    assert sample["essay"] not in public and "Fictional response 7" not in public
    restored = await run_benchmark(
        items,
        configs,
        tmp_path / "report",
        provider_factory=lambda _: pytest.fail("cache missed"),
        anchor_source=source,
        resume=True,
    )
    assert all(r["cache_hit"] for r in restored["records"])


@pytest.mark.asyncio
async def test_leakage_prevents_calls_even_when_resuming(benchmark_files, tmp_path):
    path, sample = benchmark_files
    source = AnchorSource(snapshot(), frozenset({sample["id"]}))
    configs = architecture_configurations(
        Settings(_env_file=None), "anchor-pairwise", "off", source=source
    )
    with pytest.raises(BenchmarkInputError, match="BENCHMARK_ANCHOR_LEAKAGE"):
        await run_benchmark(
            load_manifest(path, "dev"),
            configs,
            tmp_path,
            provider_factory=lambda _: pytest.fail("leakage reached provider"),
            anchor_source=source,
            resume=True,
        )


async def test_self_consistency_uses_literal_three_score_median_and_variance(
    benchmark_files, tmp_path
):
    from app.providers.writing_llm.base import Completion

    path, _ = benchmark_files
    scores = iter((6, 8, 7))

    class Provider(HybridProvider):
        def __init__(self, score):
            super().__init__()
            self.score = score

        async def complete(self, messages, schema, *, options=None):
            if "score" in schema["properties"]:
                return Completion(
                    json.dumps(
                        {
                            "score": self.score,
                            "feedback": "Diễn đạt rõ.",
                            "strengths": [],
                            "improvements": [],
                        }
                    )
                )
            return await super().complete(messages, schema, options=options)

    configs = architecture_configurations(Settings(_env_file=None), "direct-self-consistency")
    report = await run_benchmark(
        load_manifest(path, "dev"),
        configs,
        tmp_path / "median",
        provider_factory=lambda _: Provider(next(scores)),
    )
    record = report["records"][0]
    assert float(record["predicted"]["cc"]) == 7 and record["repeat_spread"]["cc"] == 2
    assert record["repeat_variance"]["cc"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("middle", ["missing", "wrong"])
async def test_self_consistency_aggregates_all_perception_observations(
    benchmark_files, monkeypatch, middle
):
    from unittest.mock import AsyncMock

    from test_task1_benchmark_metrics import matrix

    from app.evaluation.task1 import runner
    from app.evaluation.task1.metrics import perception_metrics

    path, _ = benchmark_files
    item = load_manifest(path, "dev")[0]
    config = architecture_configurations(Settings(_env_file=None), "direct-self-consistency")[0]
    direct = architecture_configurations(Settings(_env_file=None), "direct")[0]
    baseline = await runner.evaluate(item, direct, lambda _: HybridProvider(), None)
    truth = matrix()
    wrong = truth.model_copy(deep=True)
    wrong.components[0].series[0].points[0].value += 1
    observations = [
        perception_metrics(truth, truth),
        perception_metrics(truth, None if middle == "missing" else wrong),
        perception_metrics(truth, None),
    ]
    records = [baseline.model_copy(update={
        "confidence": "HIGH" if index == 0 else "MEDIUM",
        "perception": {"primary": observation, "reconciled": observation},
    }) for index, observation in enumerate(observations)]
    monkeypatch.setattr(runner, "evaluate", AsyncMock(side_effect=records))
    repeated = await runner.evaluate_repeats(item, config, None, None)
    expected_exact = 18 if middle == "missing" else 35
    for stage in ("primary", "reconciled"):
        metrics = repeated.perception[stage]
        assert metrics["labelled_numeric_count"] == metrics["truth_values"] == 54
        assert metrics["exact_labelled_numeric_count"] == expected_exact
        assert metrics["exact_labelled_numeric_agreement"] == pytest.approx(expected_exact / 54)
        assert metrics["missing_values"] == (36 if middle == "missing" else 18)
        assert metrics["repeat_observation_count"] == 3
        assert metrics["perception_ok"] is False
    assert repeated.confidence == "MEDIUM"
    assert len(repeated.repeats) == 3
    reported = aggregate([repeated])["perception"]["reconciled"]
    assert reported["labelled_numeric_count"] == 54
    assert reported["perception_observation_count"] == 3
    assert reported["exact_labelled_numeric_agreement"] == pytest.approx(expected_exact / 54)


def test_private_manifest_validation_identity_and_density(tmp_path):
    bank = snapshot()
    anchors = [
        {
            **a.model_dump(mode="json"),
            "sample_id": f"private-{index}",
            "provenance": "Fictional human labels.",
        }
        for index, a in enumerate(bank.anchors)
    ]
    path = tmp_path / "anchors.json"
    payload = {"schema_version": 1, "id": str(bank.id), "version": bank.version, "anchors": anchors}
    path.write_text(json.dumps(payload), encoding="utf-8")
    source = load_anchor_manifest(path)
    assert source.snapshot == bank and source.density["cc"]["7"] == 1
    before = source.digest
    anchors[0]["human_scores"]["cc"] = 6.5
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_anchor_manifest(path).digest != before
    anchors[0]["human_scores"]["cc"] = 6.2
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BenchmarkInputError, match="BENCHMARK_ANCHOR_MANIFEST_INVALID"):
        load_anchor_manifest(path)


async def test_postgres_source_is_read_only_active_snapshot(db_session):
    from uuid import uuid4

    from sqlalchemy.ext.asyncio import async_sessionmaker

    # Exercise the actual loader on an isolated database, with committed fixtures.
    from tacs_database import disposable_database
    from test_writing_anchors import anchor_input, frozen_task

    from app.core.config import get_settings
    from app.models import User
    from app.models.enums import UserRole
    from app.services.writing_anchors import WritingAnchorService

    async with disposable_database() as (engine, url):
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            async with session.begin():
                user = User(
                    id=uuid4(),
                    email=f"fictional-{uuid4()}@example.test",
                    display_name="Admin",
                    password_hash="fictional",
                    role=UserRole.ADMIN,
                    is_active=True,
                )
                session.add(user)
            task = await frozen_task(session)
            svc = WritingAnchorService(session)
            draft = await svc.create_draft(user.id, "Private bank")
            await svc.create_anchor(user.id, draft.id, anchor_input(task.id))
            await svc.activate(user.id, draft.id)
            before = await svc.active_snapshot()
            loaded = await load_postgres_anchors(
                get_settings().model_copy(update={"database_url": url})
            )
            assert loaded.snapshot == before == await svc.active_snapshot()
