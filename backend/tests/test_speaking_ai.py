"""Score-first Speaking contracts, with fake providers only."""

import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.providers.speaking_llm.base import Completion, CompletionOptions
from app.schemas.speaking_grading import CriterionBandScore, CriterionFeedback
from app.services.speaking_scorer import (
    SpeakingScorer,
    build_attempt_evidence,
    criterion_evidence,
    speaking_overall,
)


class FakeProvider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def complete(self, messages, schema, *, options=None):
        self.calls.append((messages, schema, options))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output if isinstance(output, Completion) else Completion(json.dumps(output))


def evidence(*, features=None):
    return build_attempt_evidence(
        [
            {
                "response_id": uuid4(),
                "prompt_id": uuid4(),
                "part_number": part,
                "prompt_type": "LONG_TURN" if part == 2 else "SHORT_ANSWER",
                "prompt_text": f"Fictional practice prompt {part}",
                "cue_points": ["A fictional detail"],
                "verbatim": f"I um enjoy a fictional activity in part {part}.",
                "clean": f"I enjoy a fictional activity in part {part}.",
                "words": [],
                "features": features,
                "scratch_notes": "PRIVATE_SCRATCH_MARKER",
                "storage_key": "/private/audio.webm",
                "unknown_metadata": "PRIVATE_UNKNOWN_MARKER",
            }
            for part in (1, 2, 3)
        ]
    )


def feature_bundle():
    return {
        "cache_key": "features",
        "source_audio_fingerprint": "audio",
        "quality": {
            "state": "AUDIO_OK",
            "assessable": True,
            "cache_key": "quality",
            "source_audio_fingerprint": "audio",
            "config": {},
            "metrics": {
                "duration_seconds": 10,
                "speech_seconds": 8,
                "rms": 0.1,
                "clipping_ratio": 0,
                "background_proxy_ratio": 0,
            },
        },
        "fluency": {
            "timing_status": "COMPLETE",
            "total_duration_seconds": 10,
            "word_count": 8,
            "aligned_word_count": 8,
            "timing_coverage": 1,
            "filled_pause_count": 1,
            "token_repetition_count": 0,
            "phrase_repetition_count": 0,
            "false_start_count": 0,
            "self_correction_count": 0,
        },
        "pronunciation": {
            "status": "AVAILABLE",
            "version": "alignment-prosody-v1",
            "source_audio_fingerprint": "audio",
            "alignment_word_count": 8,
            "alignment_coverage": 1,
            "confidence_coverage": 1,
            "mean_alignment_confidence": 0.9,
            "rms": 0.1,
            "energy_cv": 0.2,
            "acoustic_frame_count": 30,
            "word_duration_cv": 0.3,
        },
    }


FEEDBACK = {
    "feedback": "The response develops ideas with some hesitation.",
    "strengths": ["Clear fictional examples"],
    "improvements": ["Link ideas smoothly"],
}


async def checkpoint(_result):
    return None


@pytest.mark.parametrize("score", [0, 0.5, 6, 6.5, 9])
def test_half_bands_accept_valid_numbers(score):
    assert CriterionBandScore(score=score).score == score


@pytest.mark.parametrize("score", [6.3, -1, 9.5, True, "6.5", float("nan"), float("inf")])
def test_half_bands_reject_invalid_values(score):
    with pytest.raises(ValidationError):
        CriterionBandScore(score=score)


def test_feedback_has_no_score_and_bounded_contract():
    with pytest.raises(ValidationError):
        CriterionFeedback(**FEEDBACK, score=9)
    with pytest.raises(ValidationError):
        CriterionFeedback(**{**FEEDBACK, "strengths": ["x"] * 7})


@pytest.mark.parametrize("criterion", ["fc", "lr", "gra", "pr"])
async def test_whole_attempt_score_only_cap_and_checkpoint_before_feedback(criterion):
    provider = FakeProvider({"score": 6.5}, FEEDBACK)
    checkpoints = []

    async def persist(result):
        assert len(provider.calls) == 1
        assert result.score == 6.5 and result.status == "SCORE_READY"
        checkpoints.append(result)

    result = await SpeakingScorer(provider).score_criterion(
        criterion, evidence(features=feature_bundle()), persist
    )
    assert result.score == 6.5 and result.status == "COMPLETED"
    assert len(checkpoints) == 1 and len(provider.calls) == 2
    messages, schema, options = provider.calls[0]
    assert set(schema["properties"]) == {"score"}
    assert isinstance(options, CompletionOptions) and 128 <= options.max_tokens <= 256
    payload = json.loads(messages[1]["content"])
    assert len(payload["responses"]) == 3
    assert {row["part_number"] for row in payload["responses"]} == {1, 2, 3}
    prompt = json.dumps(messages)
    assert "PRIVATE_SCRATCH_MARKER" not in prompt
    assert "PRIVATE_UNKNOWN_MARKER" not in prompt
    assert "/private/audio.webm" not in prompt
    assert "per-question" in messages[0]["content"]


def test_criterion_input_separation_and_no_notes():
    item = evidence(features=feature_bundle())
    fc = criterion_evidence("fc", item)
    lr = criterion_evidence("lr", item)
    gra = criterion_evidence("gra", item)
    pr = criterion_evidence("pr", item)
    assert fc.responses[0].fluency is not None
    assert fc.responses[0].verbatim
    assert lr.responses[0].fluency is None and gra.responses[0].pronunciation is None
    assert pr.responses[0].pronunciation.acoustic_frame_count == 30
    assert "scratch" not in json.dumps(fc.model_dump(mode="json"))
    assert "source_audio_fingerprint" not in json.dumps(pr.model_dump(mode="json"))


async def test_invalid_score_gets_exactly_one_bounded_repair():
    provider = FakeProvider({"score": 6.3}, {"score": 6.5}, FEEDBACK)
    result = await SpeakingScorer(provider).score_criterion("fc", evidence(), checkpoint)
    assert result.score == 6.5 and len(provider.calls) == 3
    assert all(call[2].max_tokens == 192 for call in provider.calls[:2])
    assert "repair" in provider.calls[1][0][0]["content"].lower()


async def test_repair_failure_never_fabricates_score_or_calls_feedback():
    provider = FakeProvider({"score": 6.3}, {"score": 6.3})
    result = await SpeakingScorer(provider).score_criterion("lr", evidence(), checkpoint)
    assert result.score is None and result.status == "FAILED"
    assert result.error_code == "SPEAKING_AI_INVALID_SCORE" and len(provider.calls) == 2


@pytest.mark.parametrize(
    "failure", [RuntimeError("SECRET_TOKEN private transcript"), {**FEEDBACK, "score": 9}]
)
async def test_feedback_failure_preserves_score_and_safe_evidence(failure):
    provider = FakeProvider({"score": 6.5}, failure)
    result = await SpeakingScorer(provider).score_criterion("gra", evidence(), checkpoint)
    assert result.score == 6.5 and result.status == "FEEDBACK_FAILED"
    assert result.feedback_status == "FAILED"
    assert result.feedback.strengths == result.feedback.improvements == []
    assert len(result.evidence.responses) == 3
    assert "SECRET_TOKEN" not in result.model_dump_json()


async def test_checkpoint_failure_prevents_feedback():
    provider = FakeProvider({"score": 6.5}, FEEDBACK)

    async def cannot_persist(_):
        raise RuntimeError("checkpoint unavailable")

    with pytest.raises(RuntimeError, match="checkpoint unavailable"):
        await SpeakingScorer(provider).score_criterion("fc", evidence(), cannot_persist)
    assert len(provider.calls) == 1


async def test_provider_failure_safe_no_score_and_no_repair():
    provider = FakeProvider(RuntimeError("SECRET_TOKEN candidate transcript /private.wav"))
    result = await SpeakingScorer(provider).score_criterion("lr", evidence(), checkpoint)
    assert result.score is None and result.error_code == "SPEAKING_AI_PROVIDER_FAILED"
    assert len(provider.calls) == 1 and "SECRET_TOKEN" not in result.model_dump_json()


@pytest.mark.parametrize(
    "mutation", ["text_only", "unavailable", "low", "quality", "fake_available"]
)
async def test_pr_refuses_insufficient_or_bad_audio(mutation):
    bundle = feature_bundle()
    if mutation == "unavailable":
        bundle["pronunciation"]["status"] = "UNAVAILABLE"
    elif mutation == "low":
        bundle["pronunciation"]["status"] = "LOW_EVIDENCE"
        bundle["pronunciation"]["word_duration_cv"] = None
    elif mutation == "quality":
        bundle["quality"]["state"] = "VERY_LOW_SIGNAL"
        bundle["quality"]["assessable"] = False
    elif mutation == "fake_available":
        bundle["pronunciation"]["acoustic_frame_count"] = 0
        bundle["pronunciation"]["rms"] = None
        bundle["pronunciation"]["energy_cv"] = None
    provider = FakeProvider()
    result = await SpeakingScorer(provider).score_criterion(
        "pr", evidence(features=None if mutation == "text_only" else bundle), checkpoint
    )
    assert result.status == "UNAVAILABLE" and result.score is None
    assert (
        result.error_code
        == ("SPEAKING_AUDIO_UNASSESSABLE" if mutation == "quality" else "SPEAKING_PR_UNASSESSABLE")
        and not provider.calls
    )


@pytest.mark.parametrize(
    "completion",
    [
        Completion('{"score":6.5}', finish_reason="length"),
        Completion('{"score":6.5,"reasoning":"secret"}'),
        Completion("x" * 2000),
    ],
)
async def test_unsafe_score_envelopes_get_bounded_repair(completion):
    provider = FakeProvider(completion, {"score": 6}, FEEDBACK)
    result = await SpeakingScorer(provider).score_criterion("fc", evidence(), checkpoint)
    assert result.score == 6 and len(provider.calls) == 3
    assert "secret" not in json.dumps(provider.calls[1][0])


def test_equal_weight_raw_mean_and_project_half_band_rounding():
    assert speaking_overall({"fc": 6, "lr": 6.5, "gra": 7, "pr": 7.5}) == (6.75, 7)
    assert speaking_overall({"fc": Decimal("6"), "lr": 6, "gra": 6, "pr": 6.5}) == (6.125, 6)
    assert speaking_overall({"fc": 9, "lr": 9, "gra": 9, "pr": None}) == (None, None)
    assert speaking_overall({"fc": 9}) == (None, None)
    with pytest.raises(ValidationError):
        speaking_overall({"fc": 6.3, "lr": 6, "gra": 6, "pr": 6})


def test_provider_config_independent_and_never_mutates_writing(monkeypatch):
    from app.core.config import Settings
    from app.providers.speaking_llm import configured

    settings = Settings(ai_writing_enabled=False, ai_writing_provider="vllm")
    monkeypatch.setattr(configured, "create_writing_provider", lambda value: value)
    overrides = SimpleNamespace(
        **{
            **settings.model_dump(),
            "speaking_ai_enabled": True,
            "speaking_ai_provider": "openai",
            "speaking_ai_model": "fictional-speaking-model",
            "speaking_ai_request_timeout_seconds": 20,
            "speaking_ai_startup_timeout_seconds": 30,
        }
    )
    delegated = configured.create_provider(overrides).delegate
    assert delegated.ai_writing_enabled is True
    assert delegated.ai_writing_provider == "openai"
    assert delegated.ai_writing_openai_model == "fictional-speaking-model"
    assert settings.ai_writing_provider == "vllm" and settings.ai_writing_enabled is False
    assert configured.provider_identity(overrides) == ("openai", "fictional-speaking-model")


async def test_low_evidence_with_measured_prosody_can_score_with_caveats():
    bundle = feature_bundle()
    bundle["pronunciation"]["status"] = "LOW_EVIDENCE"
    bundle["pronunciation"]["alignment_coverage"] = 0.5
    bundle["pronunciation"]["word_duration_cv"] = None
    bundle["pronunciation"]["voiced_pitch_frames"] = 12
    bundle["pronunciation"]["pitch_mean_hz"] = 140
    provider = FakeProvider({"score": 6}, FEEDBACK)
    result = await SpeakingScorer(provider).score_criterion(
        "pr", evidence(features=bundle), checkpoint
    )
    assert result.score == 6
    assert "LOW_EVIDENCE" in result.evidence.responses[0].pronunciation.limitations


async def test_feedback_resume_uses_stored_score_without_score_call():
    first = FakeProvider({"score": 6.5}, FEEDBACK)
    saved = []
    item = evidence(features=feature_bundle())

    async def persist(result):
        saved.append(result)

    await SpeakingScorer(first).score_criterion("fc", item, persist)
    resumed = FakeProvider(FEEDBACK)
    result = await SpeakingScorer(resumed).feedback_for_scored("fc", item, saved[0])
    assert result.score == 6.5 and result.status == "COMPLETED"
    assert len(resumed.calls) == 1
    assert set(resumed.calls[0][1]["properties"]) == {"feedback", "strengths", "improvements"}


async def test_feedback_resume_rejects_different_evidence():
    first = FakeProvider({"score": 6.5}, FEEDBACK)
    saved = []

    async def persist(result):
        saved.append(result)

    await SpeakingScorer(first).score_criterion("fc", evidence(), persist)
    resumed = FakeProvider(FEEDBACK)
    with pytest.raises(ValueError, match="does not match"):
        await SpeakingScorer(resumed).feedback_for_scored("fc", evidence(), saved[0])
    assert not resumed.calls


def test_provider_cache_identity_tracks_transport_and_caps_without_secrets():
    from app.core.config import Settings
    from app.providers.speaking_llm.configured import config_identity

    settings = Settings(ai_writing_vllm_api_key="PRIVATE_KEY_MARKER")
    original = config_identity(settings)
    changed = config_identity(
        settings.model_copy(
            update={
                "ai_writing_vllm_base_url": "http://fictional.invalid/v1",
                "speaking_ai_score_max_tokens": 256,
            }
        )
    )
    assert original != changed
    assert "PRIVATE_KEY_MARKER" not in json.dumps(original)
    assert "fictional.invalid" not in json.dumps(changed)


@pytest.mark.parametrize("body", ['{"score":6,"score":9}', '{"score":NaN}', '{"score":true}'])
async def test_score_parser_rejects_duplicates_nonfinite_and_coerced_values(body):
    provider = FakeProvider(Completion(body), {"score": 6}, FEEDBACK)
    result = await SpeakingScorer(provider).score_criterion("fc", evidence(), checkpoint)
    assert result.score == 6 and len(provider.calls) == 3


def test_p5_computed_metrics_roundtrip_and_unknown_nested_input_rejected():
    from app.schemas.speaking_ai import SpeakingFeatureBundle

    bundle = SpeakingFeatureBundle.model_validate(feature_bundle())
    dumped = bundle.model_dump()
    assert "silence_ratio" in dumped["quality"]["metrics"]
    assert evidence(features=dumped).responses[0].features.quality.metrics.duration_seconds == 10
    assert "silence_ratio" in dumped["quality"]["metrics"]  # Projection did not mutate source.
    dumped["quality"]["private_path"] = "/private.wav"
    with pytest.raises(ValidationError):
        evidence(features=dumped)


def test_checkpoint_contract_rejects_boolean_band():
    from app.schemas.speaking_grading import CriterionResult

    with pytest.raises(ValidationError):
        CriterionResult(
            criterion="fc",
            status="SCORE_READY",
            score=True,
            evidence=criterion_evidence("fc", evidence()),
        )


@pytest.mark.parametrize("criterion", ["fc", "lr", "gra", "pr"])
@pytest.mark.parametrize(
    "state",
    [
        "NO_SPEECH",
        "TOO_SHORT",
        "AUDIO_CORRUPT",
        "VERY_LOW_SIGNAL",
        "SEVERE_CLIPPING",
        "BACKGROUND_DOMINANT",
        "ASR_UNUSABLE",
    ],
)
async def test_any_criterion_refuses_supplied_unassessable_quality(criterion, state):
    bundle = feature_bundle()
    bundle["quality"].update(state=state, assessable=False)
    provider = FakeProvider({"score": 1}, FEEDBACK)
    result = await SpeakingScorer(provider).score_criterion(
        criterion, evidence(features=bundle), checkpoint
    )
    assert result.status == "UNAVAILABLE" and result.score is None
    assert result.error_code == "SPEAKING_AUDIO_UNASSESSABLE" and not provider.calls


@pytest.mark.parametrize("criterion", ["fc", "lr", "gra", "pr"])
async def test_any_criterion_refuses_inconsistent_assessable_flag(criterion):
    bundle = feature_bundle()
    bundle["quality"]["assessable"] = False
    provider = FakeProvider({"score": 1}, FEEDBACK)
    result = await SpeakingScorer(provider).score_criterion(
        criterion, evidence(features=bundle), checkpoint
    )
    assert result.status == "UNAVAILABLE" and result.score is None and not provider.calls


def test_gra_utterances_preserve_verbatim_errors_and_are_criterion_specific():
    item = evidence(features=feature_bundle())
    item.responses[
        0
    ].verbatim = "I um go yesterday.  She don't agree! Why we was late? A false- start"
    gra = criterion_evidence("gra", item)
    assert gra.responses[0].utterances == [
        "I um go yesterday.",
        "She don't agree!",
        "Why we was late?",
        "A false- start",
    ]
    for criterion in ("fc", "lr", "pr"):
        assert criterion_evidence(criterion, item).responses[0].utterances is None


def test_gra_utterance_projection_is_bounded_without_dropping_verbatim():
    item = evidence()
    item.responses[0].verbatim = "a. " * 1000
    gra = criterion_evidence("gra", item)
    assert 1 <= len(gra.responses[0].utterances) <= 200
    assert all(len(utterance) <= 60000 for utterance in gra.responses[0].utterances)
    assert gra.responses[0].verbatim == item.responses[0].verbatim
    assert " ".join(gra.responses[0].utterances) == item.responses[0].verbatim.strip()
