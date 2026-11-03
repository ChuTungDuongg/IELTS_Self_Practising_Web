"""CPU evidence cannot become pronunciation bands or fabricate missing speech."""

from dataclasses import replace

from test_speaking_ai import evidence, feature_bundle
from test_speaking_features import audio, words

from app.services.speaking_features import extract_hybrid_fluency
from app.services.speaking_scorer import (
    criterion_evidence,
    fluency_assessable,
    pronunciation_assessable,
)
from app.services.speaking_vad import VadResult


def test_vad_is_speech_denominator_and_asr_fillers_are_unknown(tmp_path):
    source = audio(tmp_path)
    result = extract_hybrid_fluency(
        source, "I think so", words(), VadResult(available=True, spans=[(1000, 3500), (6500, 7500)])
    )
    assert result.detected_speech_ms == 3500 and result.articulation_rate == 3 * 60 / 3.5
    assert result.filled_pause_count is None
    assert [e.kind for e in result.events] == [
        "leading_silence",
        "speech_run",
        "pause",
        "speech_run",
        "trailing_silence",
    ]
    assert result.events[2].start_ms == 3500 and result.events[2].end_ms == 6500
    assert all(e.context == "unknown" for e in result.events)


def test_no_vad_or_missing_timing_does_not_infer_silence_from_words(tmp_path):
    result = extract_hybrid_fluency(
        audio(tmp_path), "Yesterday I go", [], VadResult(available=False)
    )
    assert result.temporal_eligible is False and result.speech_duration_seconds is None
    assert result.pause_count is None and result.filled_pause_count is None
    assert result.version == "fluency-v2"


def test_known_preparation_is_excluded_but_candidate_leading_silence_kept(tmp_path):
    source = replace(audio(tmp_path), response_start_ms=2000)
    result = extract_hybrid_fluency(
        source, "Yesterday I go", [], VadResult(available=True, spans=[(4000, 8000)])
    )
    assert result.response_window_ms == 8000
    assert result.events[0].kind == "leading_silence" and result.events[0].start_ms == 2000


def test_pitch_and_energy_cannot_unlock_hybrid_pr_or_overall():
    bundle = feature_bundle()
    bundle["profile"] = "speaking_hybrid_v1"
    bundle["version"] = "evidence-v2"
    assert not pronunciation_assessable(evidence(features=bundle))
    assert not fluency_assessable(evidence(features=bundle))


def test_new_fluency_version_and_limitations_survive_projection():
    bundle = feature_bundle()
    bundle["profile"] = "speaking_hybrid_v1"
    bundle["fluency"].update(
        version="fluency-v2",
        limitations=["ASR_DISFLUENCIES_NOT_GUARANTEED"],
        temporal_eligible=False,
    )
    projected = criterion_evidence("fc", evidence(features=bundle))
    assert projected.responses[0].fluency.version == "fluency-v2"
    assert projected.responses[0].fluency.limitations == ["ASR_DISFLUENCIES_NOT_GUARANTEED"]
    assert criterion_evidence("lr", evidence(features=bundle)).responses[0].fluency is None


def hybrid_attempt(durations=(2, 25, 2), *, partial=False):
    from app.schemas.speech_analysis import (
        SpeechAnalysisIdentity,
        SpeechAnalysisResult,
        SpeechAnalysisSource,
        SpeechCapabilities,
        SpeechCoverage,
        SpeechObservation,
        SpeechWord,
    )

    result = evidence(features=feature_bundle())
    for response, seconds in zip(result.responses, durations, strict=True):
        feature = response.features
        feature.profile = "speaking_hybrid_v1"
        feature.fluency.temporal_eligible = True
        feature.fluency.detected_speech_ms = seconds * 1000
        feature.fluency.total_duration_seconds = seconds
        feature.quality.metrics.duration_seconds = seconds
        feature.quality.metrics.speech_seconds = min(2, seconds)
        words = [
            SpeechWord(
                evidence_id=f"{response.response_id}_w{i}",
                text="fictional",
                utterance_id="u",
                start_ms=i * 1000,
                end_ms=(i + 1) * 1000,
                recognition_confidence=None,
            )
            for i in range(seconds)
        ]
        observations = [
            SpeechObservation(
                evidence_id=f"{w.evidence_id}_accuracy",
                kind="pronunciation",
                target_id=w.evidence_id,
                metric="AccuracyScore",
                score=10,
                start_ms=w.start_ms,
                end_ms=w.end_ms,
            )
            for w in words
        ]
        analysis = SpeechAnalysisResult(
            provider=SpeechAnalysisIdentity(
                provider="azure-speech",
                adapter_version="v1",
                locale="en-US",
                configuration_fingerprint="fixture",
            ),
            source=SpeechAnalysisSource(
                audio_fingerprint="audio",
                normalized_audio_fingerprint="fixture",
                duration_ms=seconds * 1000,
                response_id=str(response.response_id),
            ),
            status="PARTIAL" if partial else "COMPLETE",
            lexical_transcript=response.verbatim,
            words=words,
            observations=observations,
            coverage=SpeechCoverage(
                audio_duration_ms=seconds * 1000,
                stream_completed=not partial,
                word_count=seconds,
                recognized_span_ms=seconds * 1000,
            ),
            capabilities=SpeechCapabilities(pronunciation_observed=True),
        )
        feature.speech_analysis = [analysis]
        feature.pronunciation.observations = observations
        feature.pronunciation.evidence_coverage = 1
        feature.pronunciation.assessed_speech_ms = seconds * 1000
    return result


def test_pr_coverage_is_attempt_level_not_equal_minimum_per_question():
    assert pronunciation_assessable(hybrid_attempt())
    assert fluency_assessable(hybrid_attempt())
    assert not pronunciation_assessable(hybrid_attempt((1, 2, 1)))
    assert not pronunciation_assessable(hybrid_attempt(partial=True))
    assert not fluency_assessable(hybrid_attempt(partial=True))


async def test_provider_accuracy_is_not_a_linear_ielts_band_or_cross_criterion_anchor():
    from test_speaking_ai import FEEDBACK, FakeProvider, checkpoint

    from app.services.speaking_scorer import SpeakingScorer

    item = hybrid_attempt()
    provider = FakeProvider({"score": 6.5}, FEEDBACK)
    result = await SpeakingScorer(provider).score_criterion("pr", item, checkpoint)
    assert result.score == 6.5  # AccuracyScore=10 supplies evidence, never maps to a band.
    pr_payload = criterion_evidence("pr", item).model_dump_json()
    assert "alignment_coverage" not in pr_payload and "pitch_mean_hz" not in pr_payload
    lr = criterion_evidence("lr", item).model_dump_json()
    assert "AccuracyScore" not in lr and "words_per_minute" not in lr
    assert "RECOGNITION_CONFIDENCE_UNKNOWN" in lr


async def test_missing_temporal_evidence_prevents_fc_call_and_overall_without_losing_lr_score():
    from test_speaking_ai import FEEDBACK, FakeProvider, checkpoint

    from app.services.speaking_scorer import SpeakingScorer, speaking_overall

    item = hybrid_attempt()
    item.responses[0].features.fluency.temporal_eligible = False
    provider = FakeProvider({"score": 7}, FEEDBACK)
    scorer = SpeakingScorer(provider)
    fc = await scorer.score_criterion("fc", item, checkpoint)
    assert fc.score is None and not provider.calls
    lr = await scorer.score_criterion("lr", item, checkpoint)
    assert lr.score == 7
    assert speaking_overall({"fc": None, "lr": 7, "gra": 7, "pr": 7}) == (None, None)


def test_profile_missing_credentials_never_claims_configured_and_does_not_break_writing():
    from app.core.config import Settings
    from app.services.speaking_profile import hybrid_profile_status

    settings = Settings(
        speaking_profile="speaking_hybrid_v1",
        speaking_azure_key=None,
        speaking_azure_region="",
        speaking_asr_enabled=True,
    )
    status = hybrid_profile_status(settings)
    assert not status["configured"] and status["live_status"] == "LIVE_UNVERIFIED"
    assert settings.ai_writing_provider  # Independent defaults still initialize.
    assert not {"key", "credential", "path"} & status.keys()


def test_full_attempt_phoneme_payload_is_bounded_without_losing_coverage_or_ids():
    from app.schemas.speech_analysis import SpeechObservation

    item = hybrid_attempt()
    for response in item.responses:
        response.features.pronunciation.observations = [
            SpeechObservation(
                evidence_id=f"{response.response_id}_phoneme_{i}",
                kind="phoneme",
                target_id="word",
                metric="AccuracyScore",
                score=i % 101,
                start_ms=i,
                end_ms=i + 1,
                token="fictional",
                source="azure-pronunciation-assessment",
                certainty="provider_measurement",
                limitations=[
                    "PROVIDER_SCORES_ARE_NOT_IELTS_BANDS",
                    "LOW_ACCURACY_DOES_NOT_IDENTIFY_SUBSTITUTION",
                ],
            )
            for i in range(1250)
        ]
    projected = criterion_evidence("pr", item)
    assert len(projected.model_dump_json()) < 200000
    for source, result in zip(item.responses, projected.responses, strict=True):
        assert (
            result.pronunciation.evidence_coverage
            == source.features.pronunciation.evidence_coverage
        )
        assert result.pronunciation.observation_count == 1250
        assert result.pronunciation.observations[-1].evidence_id.endswith("_1249")
        assert "OBSERVATIONS_STRATIFIED_SAMPLE" in result.pronunciation.limitations


def test_uncertainty_and_words_are_rebased_once_for_recovered_segment():
    from uuid import uuid4

    from app.schemas.speaking_timeline import AudioSegmentMapping
    from app.schemas.speech_analysis import SpeechUncertainty

    item = hybrid_attempt()
    row = item.responses[0]
    mapping = AudioSegmentMapping(
        response_id=row.response_id,
        take_number=1,
        segment_id=uuid4(),
        normalized_start_ms=4000,
        normalized_end_ms=6000,
        gap_before_unknown=True,
    )
    row.features.timeline = [mapping]
    analysis = row.features.speech_analysis[0]
    analysis.source.segment_id = str(mapping.segment_id)
    analysis.uncertain_regions = [
        SpeechUncertainty(
            evidence_id="uncertain", start_ms=100, end_ms=200, reason="RECOGNITION_NO_MATCH"
        )
    ]
    projected = criterion_evidence("fc", item).responses[0]
    assert projected.recognized_words[0].start_ms == 4000
    assert projected.uncertain_regions[0].start_ms == 4100
    assert analysis.words[0].start_ms == 0, "Projection must not mutate the cached segment result"
