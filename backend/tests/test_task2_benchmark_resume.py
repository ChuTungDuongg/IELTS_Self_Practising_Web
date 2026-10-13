import asyncio
import json
from decimal import Decimal

import pytest
from test_task2_benchmark import Provider, config, item

from app.evaluation.task2.manifest import LoadedSample, load_manifest
from app.evaluation.task2.runner import fingerprint, run_benchmark


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "openai"),
        ("model", "different-model"),
        ("endpoint_hash", "0" * 64),
        ("prompt_version", "future-prompt"),
        ("implementation_hash", "0" * 64),
        ("max_concurrent_llm_requests", 4),
        ("request_timeout_seconds", 99),
        ("startup_timeout_seconds", 99),
        ("relevance_enabled", False),
        ("paragraph_mode", "different-provenance"),
    ],
)
def test_runtime_identity_changes(field, value):
    cfg, sample = config(), item()
    assert fingerprint(sample, cfg) != fingerprint(sample, cfg.model_copy(update={field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("essay", "Changed fictional essay"),
        ("prompt", "Changed fictional prompt"),
        ("split", "holdout"),
    ],
)
def test_sample_semantics_invalidate_identity(field, value):
    original = item()
    changed = LoadedSample(original.sample.model_copy(update={field: value}))
    assert fingerprint(original, config()) != fingerprint(changed, config())


def test_labels_change_identity_presentation_and_path_do_not(tmp_path):
    original, cfg = item(), config()
    changed = LoadedSample(
        original.sample.model_copy(
            update={
                "human_scores": original.sample.human_scores.model_copy(update={"tr": Decimal(9)})
            }
        )
    )
    assert fingerprint(original, cfg) != fingerprint(changed, cfg)
    assert fingerprint(original, cfg) == fingerprint(
        original, cfg.model_copy(update={"label": "New caption"})
    )
    for name in ("one.jsonl", "renamed.jsonl"):
        (tmp_path / name).write_text(original.sample.model_dump_json(), encoding="utf-8")
    assert fingerprint(load_manifest(tmp_path / "one.jsonl", "dev")[0], cfg) == fingerprint(
        load_manifest(tmp_path / "renamed.jsonl", "dev")[0], cfg
    )


async def test_success_resume_failed_retry_retains_costs_and_torn_cache_recovery(tmp_path):
    cfg = config()
    first = await run_benchmark(
        [item()], cfg, tmp_path, provider_factory=lambda _: Provider(fail=("scoring", "cc"))
    )
    assert first["records"][0]["status"] == "FAILED"
    second = await run_benchmark(
        [item()], cfg, tmp_path, resume=True, provider_factory=lambda _: Provider()
    )
    assert second["records"][0]["status"] == "COMPLETED"
    assert second["operational"]["failed_attempt_count"] == 1
    assert second["operational"]["attempt_count"] == 2
    assert (
        second["operational"]["provider_calls"]
        == first["operational"]["provider_calls"] + second["aggregate"]["new_provider_calls"]
    )
    for path in (tmp_path / "cache").glob("*.json"):
        path.write_text("{torn checkpoint", encoding="utf-8")

    def forbidden(_):
        raise AssertionError("Validated completed attempt should recover without a call")

    third = await run_benchmark([item()], cfg, tmp_path, resume=True, provider_factory=forbidden)
    assert third["records"][0]["cache_hit"] is True
    assert third["aggregate"]["new_provider_calls"] == 0
    assert third["operational"]["attempt_count"] == 2


@pytest.mark.parametrize("corruption", ["json", "overall", "input_hash", "target", "split"])
async def test_inconsistent_latest_attempt_not_resumed(tmp_path, corruption):
    cfg = config()
    await run_benchmark([item()], cfg, tmp_path, provider_factory=lambda _: Provider())
    path = next((tmp_path / "attempts").rglob("*.json"))
    raw = json.loads(path.read_text(encoding="utf-8"))
    if corruption == "json":
        path.write_text("{corrupt", encoding="utf-8")
    else:
        if corruption == "overall":
            raw["predicted_overall"] = 9
        elif corruption == "input_hash":
            raw["input_hash"] = "0" * 64
        elif corruption == "target":
            raw["target"] = dict.fromkeys(("tr", "cc", "lr", "gra"), 9)
            raw["target_overall"] = 9
        else:
            raw["split"] = "holdout"
        path.write_text(json.dumps(raw), encoding="utf-8")
    report = await run_benchmark(
        [item()], cfg, tmp_path, resume=True, provider_factory=lambda _: Provider()
    )
    assert report["records"][0]["cache_hit"] is False
    assert report["aggregate"]["new_provider_calls"] > 0
    assert report["records"][0]["split"] == "dev"
    assert report["records"][0]["target_overall"] != "9"


async def test_interruption_keeps_first_success_report_and_resumes(tmp_path):
    count = 0

    class Interrupted(Provider):
        async def ensure_ready(self):
            raise asyncio.CancelledError

    def factory(_):
        nonlocal count
        count += 1
        return Provider() if count == 1 else Interrupted()

    with pytest.raises(asyncio.CancelledError):
        await run_benchmark(
            [item(), item(id="T2-002")], config(), tmp_path, provider_factory=factory
        )
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "INTERRUPTED" and report["sample_count"] == 1
    completed = await run_benchmark(
        [item(), item(id="T2-002")],
        config(),
        tmp_path,
        resume=True,
        provider_factory=lambda _: Provider(),
    )
    assert completed["sample_count"] == 2
    assert completed["records"][0]["cache_hit"] is True
    assert completed["records"][1]["cache_hit"] is False
