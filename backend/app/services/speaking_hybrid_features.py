"""Measured delivery and provider observations, with conservative eligibility, never band arithmetic."""

from statistics import mean, median

from app.schemas.speaking_ai import FluencyEvent, PronunciationEvidence
from app.services.speaking_audio import fingerprint


def extract_hybrid_fluency(audio, transcript, words, vad, *, part_number=None):
    from app.services.speaking_features import extract_fluency_features, tokens

    # Keep legacy lexical candidate counts, discard all timing-derived speech/silence estimates.
    base = extract_fluency_features(audio, transcript, words, part_number=part_number)
    values = base.model_dump()
    for name in (
        "speech_duration_seconds",
        "silence_duration_seconds",
        "speech_ratio",
        "silence_ratio",
        "articulation_rate",
        "pause_count",
        "mean_pause_seconds",
        "median_pause_seconds",
        "max_pause_seconds",
        "long_pause_count",
        "long_pause_ratio",
        "average_turn_seconds",
        "part2_sustained_seconds",
    ):
        values[name] = None
    window_start, end = audio.response_start_ms, audio.duration_ms
    if not 0 <= window_start <= end:
        raise ValueError("Invalid response window")
    values.update(
        version="fluency-v2",
        response_window_ms=end - window_start,
        words_per_minute=base.word_count * 60000 / (end - window_start)
        if end > window_start
        else None,
        temporal_eligible=False,
        filled_pause_count=base.filled_pause_count or None,
        vad_version=vad.version,
        events=[],
        speech_run_lengths_ms=[],
        limitations=[
            "LEXICAL_DISFLUENCY_PROXIES",
            "ASR_DISFLUENCIES_NOT_GUARANTEED",
            *vad.limitations,
        ],
    )
    if base.timing_status != "COMPLETE":
        values["limitations"].append("WORD_TIMING_INCOMPLETE")
    if not audio.timeline:
        values["limitations"].append("PLAYBACK_MAPPING_UNAVAILABLE")
    if audio.segment_count > 1:
        values["limitations"].append("RECOVERY_GAPS_UNKNOWN")
    if audio.segment_count > 1 and not audio.timeline:
        values["limitations"].append("RECOVERY_GAP_BOUNDARIES_UNAVAILABLE")
        vad = vad.model_copy(update={"available": False})
    if not vad.available:
        return base.__class__(**values)
    spans = [
        (max(a, window_start), min(b, end)) for a, b in vad.spans if b > window_start and a < end
    ]
    if any(a < window_start or b > end or b <= a for a, b in spans) or any(
        b[0] < a[1] for a, b in zip(spans, spans[1:], strict=False)
    ):
        raise ValueError("Invalid VAD spans")
    windows = [(m.normalized_start_ms, m.normalized_end_ms) for m in audio.timeline] or [
        (window_start, end)
    ]
    events, runs, pauses = [], [], []

    def event(kind, start, stop, token=None, provenance=None):
        events.append(
            FluencyEvent(
                evidence_id="fc_" + fingerprint([audio.cache_key, kind, start, stop, token])[:28],
                kind=kind,
                start_ms=start,
                end_ms=stop,
                token=token,
                provenance=provenance or vad.version,
            )
        )

    for left, right in windows:
        left = max(left, window_start)
        current = [(max(a, left), min(b, right)) for a, b in spans if a < right and b > left]
        if not current:
            if right > left:
                event("leading_silence", left, right)
            continue
        if current[0][0] > left:
            event("leading_silence", left, current[0][0])
        previous = None
        for start, stop in current:
            if previous is not None and start - previous >= 250:
                event("pause", previous, start)
                pauses.append((start - previous) / 1000)
            event("speech_run", start, stop)
            runs.append(stop - start)
            previous = stop
        if current[-1][1] < right:
            event("trailing_silence", current[-1][1], right)
    speech_ms = sum(runs)
    # Leading/trailing silence remains visible, distinct from within-response pauses.
    values.update(
        detected_speech_ms=speech_ms,
        temporal_eligible=speech_ms > 0,
        speech_duration_seconds=speech_ms / 1000,
        silence_duration_seconds=(end - window_start - speech_ms) / 1000,
        speech_ratio=speech_ms / (end - window_start) if end > window_start else None,
        silence_ratio=1 - speech_ms / (end - window_start) if end > window_start else None,
        articulation_rate=base.word_count * 60000 / speech_ms if speech_ms else None,
        pause_count=len(pauses),
        mean_pause_seconds=mean(pauses) if pauses else 0,
        median_pause_seconds=median(pauses) if pauses else 0,
        max_pause_seconds=max(pauses, default=0),
        long_pause_count=sum(p >= 2 for p in pauses),
        long_pause_ratio=sum(p >= 2 for p in pauses) / len(pauses) if pauses else 0,
        average_turn_seconds=mean(runs) / 1000 if runs else None,
        part2_sustained_seconds=max(runs) / 1000 if runs and part_number == 2 else None,
        events=events,
        speech_run_lengths_ms=runs,
    )
    aligned_tokens = [token for w in words for token in tokens(w.word)]
    if aligned_tokens == tokens(transcript):
        for index, word in enumerate(words):
            kind = None
            if word.word.casefold().strip(".,!?") in {"um", "uh"}:
                kind = "filled_pause_candidate"
            elif index and word.word.casefold() == words[index - 1].word.casefold():
                kind = "repetition_candidate"
            elif (
                word.word.casefold().strip(".,!?") == "mean"
                and index
                and words[index - 1].word.casefold() == "i"
            ):
                kind = "repair_candidate"
            if kind:
                event(
                    kind,
                    int(word.start * 1000),
                    int(word.end * 1000),
                    word.word,
                    "lexical-heuristic-v1",
                )
    if (
        spans
        and words
        and any(not any(a <= w.start * 1000 < w.end * 1000 <= b for a, b in spans) for w in words)
    ):
        values["limitations"].append("VAD_WORD_TIMING_DISAGREEMENT")
    return base.__class__(**values)


def pronunciation_from_analysis(audio, results):
    observations, assessed, timed_words, scored_words = [], 0, 0, 0
    mappings = {str(m.segment_id): m for m in audio.timeline}
    complete = len(results) == audio.segment_count and all(r.status == "COMPLETE" for r in results)
    for result in results:
        mapping = mappings.get(result.source.segment_id)
        offset = mapping.normalized_start_ms if mapping else 0
        assessed += result.coverage.recognized_span_ms
        timed_words += len(result.words)
        word_ids = {w.evidence_id for w in result.words}
        scored_words += len(
            {
                o.target_id
                for o in result.observations
                if o.target_id in word_ids
                and o.kind in {"pronunciation", "phoneme"}
                and o.score is not None
            }
        )
        for observation in result.observations:
            if observation.kind not in {"pronunciation", "phoneme", "syllable", "prosody"}:
                continue  # Provider fluency/composite scores never anchor PR.
            if observation.metric in {"PronScore", "CompletenessScore", "FluencyScore"}:
                continue
            observations.append(
                observation.model_copy(
                    update={
                        "response_id": result.source.response_id,
                        "segment_id": result.source.segment_id,
                        "start_ms": observation.start_ms + offset
                        if observation.start_ms is not None
                        else None,
                        "end_ms": observation.end_ms + offset
                        if observation.end_ms is not None
                        else None,
                    }
                )
            )
    coverage = scored_words / timed_words if timed_words else 0
    return PronunciationEvidence(
        status="AVAILABLE"
        if complete and observations
        else "LOW_EVIDENCE"
        if observations
        else "UNAVAILABLE",
        provider="azure-speech",
        version="azure-unscripted-evidence-v1",
        source_audio_fingerprint=audio.source_audio_fingerprint,
        observations=observations[:30000],
        evidence_coverage=coverage,
        assessed_speech_ms=assessed,
        band_eligible=complete and coverage >= 0.6 and bool(observations),
        limitations=[
            "PROVIDER_MEASUREMENT_NOT_GROUND_TRUTH",
            "ACCENT_FALSE_POSITIVES_UNCALIBRATED",
            "LOW_ACCURACY_DOES_NOT_IDENTIFY_SUBSTITUTION",
            "ASSESSED_DURATION_IS_RECOGNIZED_WINDOW",
            "PR_BAND_COVERAGE_UNCALIBRATED",
        ]
        + ([] if complete else ["SPEECH_ANALYSIS_PARTIAL"]),
    )
