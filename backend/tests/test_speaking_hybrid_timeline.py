"""Offline timeline contracts: no wall-clock reconstruction or speech edits."""

from uuid import uuid4

import pytest

from app.schemas.speaking_timeline import AudioSegmentMapping, resolve_audio_span
from app.services.speaking_vad import intervals_from_probabilities


def mapping(start=0, end=4000, **kwargs):
    return AudioSegmentMapping(
        response_id=uuid4(),
        take_number=2,
        segment_id=uuid4(),
        normalized_start_ms=start,
        normalized_end_ms=end,
        **kwargs,
    )


def test_mapping_resolves_exact_segment_and_never_crosses_recovery_gap():
    first, second = mapping(), mapping(4000, 8000, gap_before_unknown=True)
    span = resolve_audio_span([first, second], 4500, 5000)
    assert span.segment_id == second.segment_id and span.take_number == 2
    assert span.start_ms == 500 and span.end_ms == 1000
    assert resolve_audio_span([first, second], 3900, 4100) is None
    assert resolve_audio_span([], 0, 1000) is None


@pytest.mark.parametrize("start,end", [(-1, 20), (10, 9), (0, float("inf"))])
def test_invalid_mapping_is_rejected(start, end):
    with pytest.raises(ValueError):
        mapping(start, end)


def test_vad_preserves_leading_silence_and_uses_detection_threshold_only():
    spans = intervals_from_probabilities([0] * 10 + [0.9] * 12 + [0] * 10, 1024)
    assert spans == [(320, 704)]
    assert intervals_from_probabilities([0.4] * 32, 1024) == []
    assert intervals_from_probabilities([0.4] * 32, 1024, threshold=0.3) == [(0, 1024)]


def test_vad_rejects_invalid_probabilities():
    with pytest.raises(ValueError):
        intervals_from_probabilities([float("nan")], 32)


async def test_recovered_segments_use_exact_samples_and_one_call_each(tmp_path):
    import wave
    from types import SimpleNamespace

    from app.services.speaking_audio import NormalizedAudio
    from app.services.speaking_hybrid import analyze_response

    path = tmp_path / "joined.wav"
    first, second = 16001, 16015
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", ""))
        wav.writeframes(b"\x01\x00" * first + b"\x02\x00" * second)
    a = mapping(0, first // 16, normalized_start_frame=0, normalized_end_frame=first)
    b = mapping(
        first // 16,
        (first + second) // 16,
        normalized_start_frame=first,
        normalized_end_frame=first + second,
        gap_before_unknown=True,
    )
    b = b.model_copy(update={"response_id": a.response_id})
    source = NormalizedAudio(
        path, "source", "v1", "cache", (first + second) // 16, segment_count=2, timeline=(a, b)
    )
    received = []

    class Analyzer:
        async def analyze(self, audio, **identity):
            with wave.open(str(audio.path), "rb") as wav:
                received.append(wav.readframes(wav.getnframes()))
            return SimpleNamespace(status="COMPLETE", source=identity)

    result = await analyze_response(source, None, analyzer=Analyzer())
    assert received == [b"\x01\x00" * first, b"\x02\x00" * second]
    assert len(result) == 2 and result[1].source["segment_id"] == str(b.segment_id)


def test_same_transcript_different_pauses_produces_different_evidence(tmp_path):
    from test_speaking_features import audio, words

    from app.services.speaking_features import extract_hybrid_fluency
    from app.services.speaking_vad import VadResult

    source = audio(tmp_path)
    first = extract_hybrid_fluency(
        source, "I think so", words(), VadResult(available=True, spans=[(0, 2000), (4000, 8000)])
    )
    second = extract_hybrid_fluency(
        source, "I think so", words(), VadResult(available=True, spans=[(0, 4000), (6000, 8000)])
    )
    assert first.word_count == second.word_count
    assert first.events != second.events
    assert not {"band", "score"} & first.model_dump().keys()
