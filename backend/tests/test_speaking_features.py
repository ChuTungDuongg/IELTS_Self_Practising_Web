import math
from dataclasses import replace

import pytest
from test_speaking_audio import pcm

from app.core.config import Settings
from app.providers.speaking_pronunciation import create_provider
from app.schemas.speaking_ai import ASRResult, WordTiming
from app.services.speaking_features import build_feature_bundle, extract_fluency_features


def words():
    return [
        WordTiming(word="I", start=1, end=2, confidence=0.9),
        WordTiming(word="think", start=2.5, end=3.5, confidence=0.8),
        WordTiming(word="so", start=6.5, end=7.5, confidence=0.4),
    ]


def audio(tmp_path, *, seconds=10, segments=1):
    return pcm(
        tmp_path,
        [int(5000 * math.sin(n / 10)) for n in range(int(seconds * 16000))],
        segment_count=segments,
    )


def test_exact_fluency_math_and_part2_turns(tmp_path):
    evidence = extract_fluency_features(audio(tmp_path), "I think so", words(), part_number=2)
    assert evidence.total_duration_seconds == 10
    assert evidence.speech_duration_seconds == 3 and evidence.silence_duration_seconds == 7
    assert evidence.speech_ratio == 0.3 and evidence.silence_ratio == 0.7
    assert evidence.words_per_minute == 18 and evidence.articulation_rate == 60
    assert (
        evidence.pause_count == 2
        and evidence.mean_pause_seconds == 1.75
        and evidence.median_pause_seconds == 1.75
        and evidence.max_pause_seconds == 3
    )
    assert evidence.long_pause_count == 1 and evidence.long_pause_ratio == 0.5
    assert evidence.average_turn_seconds == 1.75 and evidence.part2_sustained_seconds == 2.5
    assert evidence.timing_status == "COMPLETE"


@pytest.mark.parametrize(
    "gap,count,long_count",
    [
        (0.249999, 0, 0),
        (0.25, 1, 0),
        (0.250001, 1, 0),
        (1.999999, 1, 0),
        (2, 1, 1),
        (2.000001, 1, 1),
    ],
)
def test_pause_boundaries(tmp_path, gap, count, long_count):
    alignment = [
        WordTiming(word="I", start=0, end=1),
        WordTiming(word="go", start=1 + gap, end=2 + gap),
    ]
    evidence = extract_fluency_features(audio(tmp_path), "I go", alignment)
    assert evidence.pause_count == count and evidence.long_pause_count == long_count


@pytest.mark.parametrize(
    "text,alignment,status",
    [
        ("", [], "UNAVAILABLE"),
        ("I think so", [], "UNAVAILABLE"),
        ("I think so", words()[:1], "PARTIAL"),
        ("I", [WordTiming(word="I", start=0, end=0)], "COMPLETE"),
    ],
)
def test_missing_partial_and_zero_length_timing_never_fabricate(tmp_path, text, alignment, status):
    evidence = (
        extract_fluency_features(audio(tmp_path, seconds=0.02), text, alignment)
        if not alignment or alignment[0].end == 0
        else extract_fluency_features(audio(tmp_path), text, alignment)
    )
    assert evidence.timing_status == status
    assert evidence.articulation_rate is None
    if status != "COMPLETE":
        assert evidence.pause_count is None and evidence.speech_duration_seconds is None
    assert "NaN" not in evidence.model_dump_json() and "Infinity" not in evidence.model_dump_json()


def test_recovery_does_not_invent_pause_or_add_grace(tmp_path):
    evidence = extract_fluency_features(
        audio(tmp_path, segments=2), "I think so", words(), part_number=2
    )
    assert evidence.total_duration_seconds == 10 and evidence.words_per_minute == 18
    assert (
        evidence.pause_count is None
        and evidence.average_turn_seconds is None
        and evidence.part2_sustained_seconds is None
    )
    assert "RECOVERY_GAP_BOUNDARIES_UNAVAILABLE" in evidence.limitations


def test_verbatim_disfluency_proxies_are_preserved(tmp_path):
    evidence = extract_fluency_features(
        audio(tmp_path), "um uh I I think in the park in the park I went— I mean, I go.", []
    )
    assert (
        evidence.filled_pause_count == 2
        and evidence.token_repetition_count == 1
        and evidence.phrase_repetition_count == 1
    )
    assert evidence.false_start_count == 1 and evidence.self_correction_count == 1
    assert "LEXICAL_DISFLUENCY_PROXIES" in evidence.limitations


async def test_pronunciation_requires_real_normalized_audio_not_transcript(tmp_path):
    provider = create_provider(Settings())
    with pytest.raises(ValueError):
        await provider.analyse("spoken text only", "I think so", words())
    missing = replace(audio(tmp_path), path=tmp_path / "missing.wav")
    result = await provider.analyse(missing, "I think so", words())
    assert result.status == "UNAVAILABLE" and result.error_code == "AUDIO_UNAVAILABLE"


async def test_pronunciation_acoustic_alignment_and_unsupported_features(tmp_path):
    provider, source = create_provider(Settings()), audio(tmp_path)
    result = await provider.analyse(source, "I think so", words())
    assert result == await provider.analyse(source, "I think so", words())
    assert result.status == "LOW_EVIDENCE" and result.low_confidence_spans[0].word == "so"
    assert 200 < result.pitch_mean_hz < 300 and result.rms > 0 and result.voiced_pitch_frames > 0
    assert result.word_duration_cv == 0 and result.mean_alignment_confidence == pytest.approx(0.7)
    assert (
        result.phoneme_substitutions is None
        and result.linguistic_stress is None
        and result.listener_effort is None
    )
    assert "PHONEME_ALIGNMENT_UNAVAILABLE" in result.limitations
    missing_alignment = await provider.analyse(source, "I think so", [])
    assert (
        missing_alignment.status == "LOW_EVIDENCE"
        and missing_alignment.mean_alignment_confidence is None
        and missing_alignment.word_duration_cv is None
    )
    assert not {"band", "score", "ielts_band"} & result.model_dump().keys()


async def test_pronunciation_unavailable_and_unvoiced_audio_do_not_invent_pitch(tmp_path):
    configured = Settings(speaking_pronunciation_enabled=False)
    source = pcm(tmp_path, [5000] * 32000)
    result = await create_provider(configured).analyse(source, "I think so", words())
    assert result.status == "UNAVAILABLE" and result.error_code == "PROVIDER_UNAVAILABLE"
    result = await create_provider(Settings()).analyse(source, "I think so", [])
    assert result.pitch_mean_hz is None and result.voiced_pitch_frames == 0


async def test_bundle_fingerprints_and_private_note_isolation(tmp_path):
    settings, source = Settings(), audio(tmp_path)
    transcript = ASRResult(
        text="I think so", words=words(), provider="fake", model="fixture", version="v1"
    )
    first = await build_feature_bundle(source, transcript, settings, part_number=2)
    assert first == await build_feature_bundle(source, transcript, settings, part_number=2)
    settings.speaking_pronunciation.version = "prosody-next"
    assert (
        await build_feature_bundle(source, transcript, settings, part_number=2)
    ).cache_key != first.cache_key
    assert "THIS_SECRET_NOTE_MUST_NOT_ENTER_SPEECH_ANALYSIS_98765" not in first.model_dump_json()
    assert str(tmp_path) not in first.model_dump_json()
    assert first.quality.state == "AUDIO_OK" and first.fluency.word_count == 3


def test_empty_audio_metadata_and_mismatched_alignment_are_explicit(tmp_path):
    source = replace(audio(tmp_path), duration_ms=0)
    empty = extract_fluency_features(source, "", [])
    assert empty.words_per_minute is None and empty.speech_ratio is None and empty.word_count == 0
    mismatch = extract_fluency_features(
        audio(tmp_path),
        "He go",
        [WordTiming(word="He", start=0, end=1), WordTiming(word="goes", start=1, end=2)],
    )
    assert mismatch.timing_status == "PARTIAL" and mismatch.silence_ratio is None


@pytest.mark.parametrize("offset", [-1e-6, 0, 1e-6])
async def test_low_confidence_threshold_is_evidence_only(tmp_path, offset):
    settings = Settings()
    alignment = words()
    alignment[-1].confidence = settings.speaking_pronunciation.low_confidence_threshold + offset
    evidence = await create_provider(settings).analyse(audio(tmp_path), "I think so", alignment)
    assert len(evidence.low_confidence_spans) == (1 if offset < 0 else 0)
    assert evidence.status == ("LOW_EVIDENCE" if offset < 0 else "AVAILABLE")


@pytest.mark.parametrize(
    "alignment",
    [
        [dict(word="I", start=1, end=2), dict(word="think", start=1.5, end=3)],
        [dict(word="I", start=0, end=20)],
    ],
)
def test_invalid_timings_are_not_fluency_evidence(tmp_path, alignment):
    with pytest.raises(ValueError):
        extract_fluency_features(audio(tmp_path), "I think", alignment)


async def test_feature_cache_changes_for_text_alignment_audio_and_quality(tmp_path):
    settings, source = Settings(), audio(tmp_path)
    result = ASRResult(
        text="I think so", words=words(), provider="fake", model="fixture", version="v1"
    )
    first = await build_feature_bundle(source, result, settings)
    for changed in [
        result.model_copy(update={"text": "He go"}),
        result.model_copy(update={"words": words()[:1]}),
        result.model_copy(update={"version": "v2"}),
    ]:
        assert (await build_feature_bundle(source, changed, settings)).cache_key != first.cache_key
    assert (
        await build_feature_bundle(
            replace(source, source_audio_fingerprint="new", cache_key="new"), result, settings
        )
    ).cache_key != first.cache_key
    settings.speaking_quality.minimum_rms = 0.006
    assert (await build_feature_bundle(source, result, settings)).cache_key != first.cache_key
