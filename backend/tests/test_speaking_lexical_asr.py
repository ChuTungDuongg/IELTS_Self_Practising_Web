"""Fictional lexical/acoustic disagreement; no SDK/network/model calls."""

from types import SimpleNamespace

import pytest
from test_azure_speech_analysis import final_payload, settings

from app.providers.speech_analysis.azure import AzureSpeechAnalyzer


@pytest.mark.parametrize("damage", ["phoneme", "assessment", "word_timing", "display"])
def test_optional_acoustic_damage_never_discards_valid_lexical_utterance(damage):
    analyzer = AzureSpeechAnalyzer(settings())
    audio = SimpleNamespace(
        source_audio_fingerprint="fictional", cache_key="fixture", duration_ms=60000
    )
    result = analyzer._empty(audio, None, None, None)
    raw = final_payload(text="Yesterday I go um I I mean school")
    best = raw["NBest"][0]
    if damage == "phoneme":
        best["Words"][0]["Phonemes"][0]["Duration"] = -1
    elif damage == "assessment":
        best["Words"][0]["PronunciationAssessment"] = ["invalid optional metadata"]
    elif damage == "word_timing":
        best["Words"][0]["Duration"] = -1
    else:
        best["Display"] = {"invalid": "optional display"}
    analyzer._append_final(result, raw)
    finished = analyzer._finish(audio, result, None, True)
    assert finished.lexical_transcript == "Yesterday I go um I I mean school"
    assert finished.utterances[0].recognition_confidence == 0.82
    assert finished.limitations


def test_missing_middle_word_timing_never_reorders_learner_grammar():
    import copy

    analyzer = AzureSpeechAnalyzer(settings())
    audio = SimpleNamespace(
        source_audio_fingerprint="fictional", cache_key="fixture", duration_ms=60000
    )
    result = analyzer._empty(audio, None, None, None)
    raw = final_payload(text="Yesterday I go")
    template = raw["NBest"][0]["Words"][0]
    words = []
    for index, text in enumerate(["Yesterday", "I", "go"]):
        word = copy.deepcopy(template)
        word.update(
            Word=text, Offset=17000000 + index * 2000000, Duration=-1 if index == 1 else 2000000
        )
        words.append(word)
    raw["NBest"][0]["Words"] = words
    analyzer._append_final(result, raw)
    finished = analyzer._finish(audio, result, None, True)
    assert [word.text for word in finished.words] == ["Yesterday", "I", "go"]
    assert finished.words[1].start_ms is None
    assert finished.words[0].start_ms == 1700 and finished.words[2].start_ms == 2100
    assert finished.lexical_transcript == "Yesterday I go" and finished.status == "PARTIAL"


@pytest.mark.parametrize("silence", [None, 500, 1200])
async def test_segmentation_property_is_explicit_and_versioned_without_semantic_segmentation(
    monkeypatch, tmp_path, silence
):
    import wave

    from test_azure_speech_analysis import FakeSDK, emit

    from app.services.speaking_audio import NormalizedAudio

    def recognize(recognizer):
        emit(recognizer, final_payload())
        recognizer.session_stopped.emit(None)

    sdk = FakeSDK(recognize)
    sdk.PropertyId = SimpleNamespace(
        SpeechServiceResponse_JsonResult="json", Speech_SegmentationSilenceTimeoutMs="silence"
    )
    properties = []
    original_config = sdk.SpeechConfig

    def config(**kwargs):
        result = original_config(**kwargs)
        result.set_property = lambda key, value: properties.append((key, value))
        return result

    sdk.SpeechConfig = config
    monkeypatch.setattr("app.providers.speech_analysis.azure._load_sdk", lambda: sdk)
    path = tmp_path / "synthetic.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "none"))
        stream.writeframes(b"\0\0" * 16000 * 4)
    analyzer = AzureSpeechAnalyzer(settings(speaking_azure_segmentation_silence_timeout_ms=silence))
    result = await analyzer.analyze(NormalizedAudio(path, "source", "v1", "cache", 4000))
    assert result.status == "COMPLETE"
    assert properties == ([] if silence is None else [("silence", str(silence))])
    assert ("segmentation_version" in analyzer.identity.configuration) == (silence is not None)
    assert "Semantic" not in str(properties)


async def test_standalone_azure_stt_does_not_apply_pronunciation_config(monkeypatch, tmp_path):
    import wave

    from test_azure_speech_analysis import FakeSDK, emit

    from app.services.speaking_audio import NormalizedAudio

    def recognize(recognizer):
        emit(recognizer, final_payload(text="Yesterday I go um I I mean school"))
        recognizer.session_stopped.emit(None)

    sdk = FakeSDK(recognize)

    def forbidden(**_):
        pytest.fail("STT must not attach pronunciation assessment")

    sdk.PronunciationAssessmentConfig = forbidden
    monkeypatch.setattr("app.providers.speech_analysis.azure._load_sdk", lambda: sdk)
    path = tmp_path / "synthetic.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "none"))
        stream.writeframes(b"\0\0" * 16000 * 4)
    result = await AzureSpeechAnalyzer(settings(), pronunciation=False).analyze(
        NormalizedAudio(path, "fictional", "v1", "fixture", 4000)
    )
    assert result.provider.provider == "azure-stt"
    assert result.lexical_transcript == "Yesterday I go um I I mean school"
    assert result.observations == [] and not result.capabilities.unscripted
    assert result.words[0].recognition_confidence is None  # Never reuse PA AccuracyScore.


@pytest.mark.parametrize("strategy", ["faster_whisper_local", "faster_whisper_modal"])
async def test_whisper_facade_preserves_native_words_confidence_and_model_provenance(
    monkeypatch, tmp_path, strategy
):
    import hashlib
    import wave

    from app.providers.speaking_asr.lexical import create_lexical_analyzer
    from app.schemas.speaking_ai import ASRResult, WordTiming
    from app.services.speaking_audio import NormalizedAudio

    submitted = []
    configured_providers = []

    async def transcribe(audio):
        submitted.append(audio.path)
        return ASRResult(
            text="Yesterday I go um",
            words=[
                WordTiming(word="Yesterday", start=0.1, end=0.3, confidence=None),
                WordTiming(word="I", start=0.3, end=0.4, confidence=0.2),
                WordTiming(word="go", start=0.4, end=0.5, confidence=0.95),
                WordTiming(word="um", start=0.5, end=0.6, confidence=0.4),
            ],
            provider="fixture",
            model="fictional-whisper",
            version="fictional-decode-v1",
        )

    def provider(settings):
        configured_providers.append(settings.speaking_asr_provider)
        return SimpleNamespace(transcribe=transcribe)

    monkeypatch.setattr("app.providers.speaking_asr.create_provider", provider)
    settings = configured(
        speaking_lexical_asr_provider=strategy,
        speaking_lexical_asr_allow_additional_requests=True,
        speaking_lexical_asr_allow_gpu=True,
        speaking_lexical_asr_estimated_cost_usd_per_minute=0.1,
        speaking_lexical_asr_max_estimated_cost_usd_per_response=1,
        speaking_asr_model="fictional-whisper",
        speaking_asr_version="fictional-decode-v1",
    )
    path = tmp_path / "synthetic.wav"
    pcm = b"\0\0" * 16000
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "none"))
        stream.writeframes(pcm)
    analyzer = create_lexical_analyzer(settings)
    result = await analyzer.analyze(
        NormalizedAudio(path, "source", "v1", "cache", 1000), segment_id="source-segment"
    )
    assert result.lexical_transcript == "Yesterday I go um"
    assert [word.recognition_confidence for word in result.words] == [None, 0.2, 0.95, 0.4]
    assert result.utterances[0].recognition_confidence is None and result.observations == []
    assert result.provider.provider == strategy
    assert result.provider.configuration["model"] == "fictional-whisper"
    assert result.source.normalized_audio_fingerprint == hashlib.sha256(pcm).hexdigest()
    assert result.words[0].start_ms == 100 and result.words[-1].end_ms == 600
    assert not result.capabilities.continuous_recognition
    assert result.usage.billing_uncertain == (strategy == "faster_whisper_modal")
    assert submitted == [path] and configured_providers == [
        "modal" if strategy.endswith("modal") else "local"
    ]


def configured(**updates):
    from app.core.config import Settings

    values = dict(
        speaking_asr_enabled=True,
        speaking_asr_provider="azure",
        speaking_azure_key="fictional",
        speaking_azure_region="fictional",
        speaking_azure_billing_mode="free_only",
    )
    return Settings(_env_file=None, **(values | updates))


def test_defaults_and_independent_cache_identities():
    from app.providers.speaking_asr import provider_identity
    from app.providers.speaking_asr.lexical import lexical_identity
    from app.providers.speech_analysis.azure import azure_analysis_identity
    from app.services.speaking_features import feature_identity

    original = configured()
    stt = configured(speaking_lexical_asr_provider="azure_stt")
    changed_prompt = stt.model_copy(update={"speaking_ai_prompt_version": "new-luna-prompt"})
    changed_pa = stt.model_copy(update={"speaking_azure_prosody": False})
    segmented = stt.model_copy(update={"speaking_azure_segmentation_silence_timeout_ms": 1000})
    assert "lexical" not in provider_identity(original)
    assert "lexical_projection" not in feature_identity(original)
    assert provider_identity(stt) != provider_identity(original)
    assert azure_analysis_identity(stt) == azure_analysis_identity(original)
    assert lexical_identity(changed_prompt) == lexical_identity(stt)
    assert azure_analysis_identity(changed_prompt) == azure_analysis_identity(stt)
    assert lexical_identity(changed_pa) == lexical_identity(stt)
    assert azure_analysis_identity(changed_pa) != azure_analysis_identity(stt)
    assert lexical_identity(segmented) != lexical_identity(stt)
    assert azure_analysis_identity(segmented) != azure_analysis_identity(stt)
    whisper = stt.model_copy(update={"speaking_lexical_asr_provider": "faster_whisper_modal"})
    revised = whisper.model_copy(update={"speaking_asr_model_revision": "fictional-revision"})
    assert lexical_identity(whisper) != lexical_identity(revised)
    assert azure_analysis_identity(whisper) == azure_analysis_identity(revised)
    local = whisper.model_copy(update={"speaking_lexical_asr_provider": "faster_whisper_local"})
    local_revised = local.model_copy(
        update={"speaking_asr_model_revision": "fictional-local-revision"}
    )
    assert lexical_identity(local) != lexical_identity(local_revised)
    assert azure_analysis_identity(local) == azure_analysis_identity(local_revised)


def test_second_cloud_request_requires_opt_in_and_response_budget():
    from app.core.exceptions import AppError
    from app.providers.speaking_asr.lexical import require_lexical_permission

    stt = configured(speaking_lexical_asr_provider="azure_stt")
    with pytest.raises(AppError, match="permission"):
        require_lexical_permission(stt, duration_ms=60000)
    stt = stt.model_copy(
        update={
            "speaking_lexical_asr_allow_additional_requests": True,
            "speaking_lexical_asr_estimated_cost_usd_per_minute": 0.2,
            "speaking_lexical_asr_max_estimated_cost_usd_per_response": 0.1,
        }
    )
    with pytest.raises(AppError) as error:
        require_lexical_permission(stt, duration_ms=60000)
    assert error.value.code == "SPEAKING_LEXICAL_ASR_BUDGET_EXCEEDED"
    require_lexical_permission(stt, duration_ms=10000)
    with pytest.raises(AppError):
        require_lexical_permission(stt, "faster_whisper_modal")
    require_lexical_permission(configured())  # Legacy makes no second request.


async def test_missing_second_request_consent_blocks_before_any_pa_submission(monkeypatch):
    from app.core.exceptions import AppError
    from app.services.speaking_hybrid import transcribe_hybrid

    async def forbidden(*_, **__):
        pytest.fail("No speech request may start before independent-provider admission")

    monkeypatch.setattr("app.services.speaking_analysis_cache.cached_speech_analysis", forbidden)
    with pytest.raises(AppError) as error:
        await transcribe_hybrid(
            None,
            SimpleNamespace(duration_ms=60000),
            configured(speaking_lexical_asr_provider="azure_stt"),
            None,
        )
    assert error.value.code == "SPEAKING_LEXICAL_ASR_NOT_AUTHORIZED"


def independent_evidence(*, pa_failed=False):
    from test_speaking_hybrid_features import hybrid_attempt

    from app.schemas.speech_analysis import SpeechUtterance

    evidence = hybrid_attempt()
    for response in evidence.responses:
        pa = response.features.speech_analysis[0]
        pa.lexical_transcript = "Yesterday I went"
        pa.utterances = [SpeechUtterance(evidence_id="pa-u", lexical_text="Yesterday I went")]
        lexical = pa.model_copy(deep=True)
        lexical.provider.provider = "azure-stt"
        lexical.lexical_transcript = "Yesterday I go um I I mean school"
        lexical.utterances = [
            SpeechUtterance(evidence_id="stt-u", lexical_text=lexical.lexical_transcript)
        ]
        lexical.observations = []
        lexical.words = [
            pa.words[0].model_copy(
                update={"evidence_id": "stt-w", "text": "Yesterday", "recognition_confidence": 0.3}
            )
        ]
        response.features.lexical_analysis = [lexical]
        response.verbatim = response.clean = lexical.lexical_transcript
        if pa_failed:
            pa.status = "FAILED"
    return evidence


def test_gra_lr_fc_use_canonical_grammar_and_pr_retains_separate_pa_tokens():
    from app.services.speaking_scorer import (
        criterion_evidence,
        fluency_assessable,
        pronunciation_assessable,
    )

    evidence = independent_evidence()
    for criterion in ("gra", "lr", "fc"):
        row = criterion_evidence(criterion, evidence).responses[0]
        assert row.verbatim == "Yesterday I go um I I mean school"
        assert row.recognized_words[0].evidence_id == "stt-w"
        assert row.recognized_words[0].recognition_confidence == 0.3
        assert row.recognized_words[0].start_ms == 0
        assert row.lexical_provider == "azure-stt"
        assert row.cross_provider_alignment == "not_performed"
        if criterion == "gra":
            assert row.utterances == [row.verbatim]
    pr = criterion_evidence("pr", evidence).responses[0]
    assert pr.acoustic_transcript == "Yesterday I went"
    assert pr.pronunciation.observations[0].target_id != "stt-w"
    assert pr.recognized_words == [] and "stt-w" not in pr.uncertain_word_ids
    failed = independent_evidence(pa_failed=True)
    assert not pronunciation_assessable(failed)
    assert fluency_assessable(failed), (
        "Independent lexical evidence and VAD must not depend on PA success"
    )


def test_canonical_offsets_rebase_only_their_own_provider_timing():
    from uuid import uuid4

    from app.schemas.speaking_timeline import AudioSegmentMapping
    from app.services.speaking_scorer import criterion_evidence

    evidence = independent_evidence()
    response = evidence.responses[1]
    segment_id = uuid4()
    response.features.timeline = [
        AudioSegmentMapping(
            response_id=response.response_id,
            segment_id=segment_id,
            take_number=1,
            normalized_start_ms=5000,
            normalized_end_ms=25000,
        )
    ]
    lexical = response.features.lexical_analysis[0]
    lexical.source.segment_id = str(segment_id)
    lexical.words[0].start_ms, lexical.words[0].end_ms = 100, 300
    original_pa = response.features.speech_analysis[0].model_dump()
    for criterion in ("gra", "lr", "fc"):
        word = criterion_evidence(criterion, evidence).responses[1].recognized_words[0]
        assert (word.start_ms, word.end_ms, word.recognition_confidence) == (5100, 5300, 0.3)
    assert lexical.words[0].start_ms == 100
    assert response.features.speech_analysis[0].model_dump() == original_pa


async def test_modal_timeout_is_billing_uncertain_and_never_falls_back(monkeypatch):
    from app.core.exceptions import AppError
    from app.services.speaking_hybrid import transcribe_hybrid

    calls = []

    async def cache(*_, cache_namespace="speech_analysis", **__):
        calls.append(cache_namespace)
        if cache_namespace == "lexical_asr":
            raise AppError("SPEAKING_ASR_UNAVAILABLE", "fictional timeout", 503)
        return []

    monkeypatch.setattr("app.services.speaking_analysis_cache.cached_speech_analysis", cache)
    monkeypatch.setattr(
        "app.providers.speaking_asr.lexical.create_lexical_analyzer", lambda *_: object()
    )
    settings = configured(
        speaking_lexical_asr_provider="faster_whisper_modal",
        speaking_lexical_asr_allow_additional_requests=True,
        speaking_lexical_asr_allow_gpu=True,
        speaking_lexical_asr_estimated_cost_usd_per_minute=0.1,
        speaking_lexical_asr_max_estimated_cost_usd_per_response=1,
    )
    with pytest.raises(AppError) as error:
        await transcribe_hybrid(None, SimpleNamespace(duration_ms=1000), settings, None)
    assert error.value.code == "SPEAKING_ANALYSIS_BILLING_UNKNOWN"
    assert calls == ["speech_analysis", "lexical_asr"]


@pytest.mark.parametrize("pa_fails,lexical_fails", [(False, False), (False, True), (True, False)])
async def test_coordinator_uses_explicit_source_without_paid_fallback(
    monkeypatch, pa_fails, lexical_fails
):
    from app.core.exceptions import AppError
    from app.schemas.speech_analysis import (
        SpeechAnalysisIdentity,
        SpeechAnalysisResult,
        SpeechAnalysisSource,
        SpeechCoverage,
    )
    from app.services.speaking_hybrid import transcribe_hybrid

    calls = []

    async def cache(*_, cache_namespace="speech_analysis", **__):
        calls.append(cache_namespace)
        lexical = cache_namespace == "lexical_asr"
        failed = lexical_fails if lexical else pa_fails
        return [
            SpeechAnalysisResult(
                provider=SpeechAnalysisIdentity(
                    provider="azure-stt" if lexical else "azure-speech",
                    adapter_version="fixture",
                    locale="en-US",
                    configuration_fingerprint="fixture",
                ),
                source=SpeechAnalysisSource(
                    audio_fingerprint="source", normalized_audio_fingerprint="pcm", duration_ms=1000
                ),
                status="FAILED" if failed else "COMPLETE",
                lexical_transcript=""
                if failed
                else "Yesterday I go"
                if lexical
                else "Yesterday I went",
                coverage=SpeechCoverage(audio_duration_ms=1000, stream_completed=not failed),
                capabilities={},
            )
        ]

    monkeypatch.setattr("app.services.speaking_analysis_cache.cached_speech_analysis", cache)
    stt = configured(
        speaking_lexical_asr_provider="azure_stt",
        speaking_lexical_asr_allow_additional_requests=True,
        speaking_lexical_asr_estimated_cost_usd_per_minute=0.1,
        speaking_lexical_asr_max_estimated_cost_usd_per_response=1,
    )
    audio = SimpleNamespace(duration_ms=1000, timeline=[], source_audio_fingerprint="source")
    if lexical_fails:
        with pytest.raises(AppError) as error:
            await transcribe_hybrid(None, audio, stt, None)
        assert error.value.code == "ASR_UNUSABLE"
    else:
        result, pa, lexical = await transcribe_hybrid(None, audio, stt, None)
        assert result.text == "Yesterday I go" and result.provider == "azure-stt"
        assert pa[0].status == ("FAILED" if pa_fails else "COMPLETE")
    assert calls == ["speech_analysis", "lexical_asr"]


async def test_default_one_pass_does_not_construct_independent_provider(monkeypatch):
    from app.services.speaking_hybrid import transcribe_hybrid

    async def cache(*_, **__):
        return [
            SimpleNamespace(
                source=SimpleNamespace(audio_fingerprint="source", segment_id=None),
                lexical_transcript="Yesterday I go",
                words=[],
                provider=SimpleNamespace(locale="en-US"),
                error_code=None,
            )
        ]

    def forbidden(*_):
        pytest.fail("Default azure_pa must never construct another recognizer")

    monkeypatch.setattr("app.services.speaking_analysis_cache.cached_speech_analysis", cache)
    monkeypatch.setattr("app.providers.speaking_asr.lexical.create_lexical_analyzer", forbidden)
    result, _, lexical = await transcribe_hybrid(
        None,
        SimpleNamespace(duration_ms=1000, timeline=[], source_audio_fingerprint="source"),
        configured(),
        None,
    )
    assert result.text == "Yesterday I go" and lexical is None


def test_independent_service_failure_is_not_reported_as_candidate_audio_failure():
    from app.core.exceptions import AppError
    from app.services.speaking_hybrid import analysis_to_asr

    result = SimpleNamespace(
        source=SimpleNamespace(audio_fingerprint="source"),
        lexical_transcript="",
        error_code="AZURE_UNAVAILABLE",
    )
    with pytest.raises(AppError) as error:
        analysis_to_asr(
            [result],
            SimpleNamespace(source_audio_fingerprint="source", timeline=[]),
            independent=True,
        )
    assert error.value.code == "SPEAKING_LEXICAL_ASR_UNAVAILABLE"


async def test_durable_worker_caches_providers_separately_and_preserves_history(
    db_session, tmp_path, monkeypatch
):
    from sqlalchemy import select
    from test_speaking_hybrid_worker import Analyzer
    from test_speaking_transcript import completed, worker_for

    from app.models.speaking_transcript import SpeakingNormalizedAudio, SpeakingTranscript
    from app.providers.speaking_asr import provider_identity
    from app.providers.speaking_asr.lexical import lexical_identity
    from app.services.speaking_transcript import SpeakingTranscriptService

    aid, rid, media = await completed(db_session, tmp_path)
    settings = configured(
        speaking_lexical_asr_provider="azure_stt",
        speaking_lexical_asr_allow_additional_requests=True,
        speaking_lexical_asr_estimated_cost_usd_per_minute=0.1,
        speaking_lexical_asr_max_estimated_cost_usd_per_response=1,
    )
    pa = Analyzer(settings)
    lexical = Analyzer(settings)
    lexical.identity = lexical_identity(settings)
    monkeypatch.setattr(
        "app.providers.speaking_asr.lexical.create_lexical_analyzer", lambda *_: lexical
    )
    provider = SimpleNamespace(identity=provider_identity(settings), analyzer=pa)
    service = SpeakingTranscriptService(
        db_session, media.actor, settings, identity=provider.identity
    )
    first = await service.create(aid)
    await worker_for(db_session, settings, media.storage, provider).execute(first.run_id)
    snapshot = await service.get(aid, first.run_id)
    assert snapshot.status == "COMPLETED" and snapshot.responses[0].verbatim == "Yesterday I go"
    assert len(pa.calls) == len(lexical.calls) == 1
    assert (await service.create(aid)).cache_hit
    assert len(pa.calls) == len(lexical.calls) == 1
    prompt_changed = settings.model_copy(
        update={"speaking_ai_prompt_version": "fictional-new-prompt"}
    )
    assert (
        await SpeakingTranscriptService(
            db_session, media.actor, prompt_changed, identity=provider.identity
        ).create(aid)
    ).cache_hit
    assert len(pa.calls) == len(lexical.calls) == 1
    async with db_session.begin():
        normalized = await db_session.scalar(
            select(SpeakingNormalizedAudio).where(SpeakingNormalizedAudio.response_id == rid)
        )
        assert (
            len(normalized.metadata_json["speech_analysis"])
            == len(normalized.metadata_json["lexical_asr"])
            == 1
        )
        frozen = (
            await db_session.scalars(
                select(SpeakingTranscript).where(SpeakingTranscript.response_id == rid)
            )
        ).all()
        frozen_ids = {row.id for row in frozen}
    # A new lexical model version changes only the lexical checkpoint and feature/scorer identity.
    changed = settings.model_copy()
    lexical.identity = lexical.identity.model_copy(update={"adapter_version": "fixture-stt-v2"})
    changed_identity = {**provider.identity, "lexical": lexical.identity.model_dump(mode="json")}
    provider2 = SimpleNamespace(identity=changed_identity, analyzer=pa)
    next_service = SpeakingTranscriptService(
        db_session, media.actor, changed, identity=changed_identity
    )
    assert await next_service.latest(aid) is None  # Existing current-identity semantics.
    historical = await next_service.get(aid, first.run_id)
    assert (
        historical.run_id == first.run_id and historical.responses[0].verbatim == "Yesterday I go"
    )
    second = await next_service.create(aid)
    await worker_for(db_session, changed, media.storage, provider2).execute(second.run_id)
    assert (await next_service.get(aid, second.run_id)).status == "COMPLETED"
    assert len(pa.calls) == 1 and len(lexical.calls) == 2
    async with db_session.begin():
        rows = (
            await db_session.scalars(
                select(SpeakingTranscript).where(SpeakingTranscript.response_id == rid)
            )
        ).all()
        assert frozen_ids < {row.id for row in rows}
        assert all(row.text == "Yesterday I go" for row in rows)


@pytest.mark.parametrize("namespace", ["speech_analysis", "lexical_asr"])
async def test_interrupted_provider_checkpoint_cannot_resubmit_without_explicit_consent(
    db_session, tmp_path, namespace
):
    import asyncio

    from test_speaking_hybrid_worker import Analyzer
    from test_speaking_transcript import completed, fake_decode, worker_for

    from app.core.exceptions import AppError
    from app.services.speaking_analysis_cache import cached_speech_analysis
    from app.services.speaking_audio import normalize_committed_take, stage_normalized_audio

    _, rid, media = await completed(db_session, tmp_path)
    settings = configured()
    analyzer = Analyzer(settings)
    calls = []

    async def interrupted(*_, **__):
        calls.append(1)
        raise asyncio.CancelledError()

    analyzer.analyze = interrupted
    worker = worker_for(db_session, settings, media.storage, None)
    ref = await normalize_committed_take(
        db_session, rid, settings, storage=media.storage, executor=fake_decode
    )
    async with stage_normalized_audio(media.storage, ref, 600) as audio:
        with pytest.raises(asyncio.CancelledError):
            await cached_speech_analysis(
                worker.sessions, audio, settings, analyzer, cache_namespace=namespace
            )
        with pytest.raises(AppError) as error:
            await cached_speech_analysis(
                worker.sessions, audio, settings, analyzer, cache_namespace=namespace
            )
        assert error.value.code == "SPEAKING_ANALYSIS_BILLING_UNKNOWN" and len(calls) == 1
