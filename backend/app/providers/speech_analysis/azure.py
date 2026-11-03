"""Optional Azure SDK boundary; no reference text, raw payload persistence or retries."""

import asyncio
import copy
import hashlib
import importlib.metadata
import json
import math
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.providers.speech_analysis.azure_policy import (
    AUTHENTICATION_FAILED,
    BILLING_BLOCKED,
    QUOTA_EXCEEDED,
    billing_authorized,
    quota_reason,
)
from app.schemas.speech_analysis import (
    SpeechAnalysisIdentity,
    SpeechAnalysisResult,
    SpeechAnalysisSource,
    SpeechCapabilities,
    SpeechCoverage,
    SpeechObservation,
    SpeechUncertainty,
    SpeechUsage,
    SpeechUtterance,
    SpeechWord,
)
from app.services.speaking_audio import NormalizedAudio, await_audio_thread

ADAPTER_VERSION = "azure-unscripted-v2-billing"
CLEANUP_GRACE_SECONDS = 0.25


def _load_sdk():
    import azure.cognitiveservices.speech as speechsdk

    return speechsdk


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass
class _NativePool:
    executor: ThreadPoolExecutor
    admission: threading.BoundedSemaphore


_pools: dict[tuple[int, int], _NativePool] = {}
_pool_lock = threading.Lock()


def _pool(concurrency, queue):
    with _pool_lock:
        key = (concurrency, queue)
        if key not in _pools:
            _pools[key] = _NativePool(
                ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="azure-speech"),
                threading.BoundedSemaphore(concurrency + queue),
            )
        return _pools[key]


def _number(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= maximum else None


def _span(raw, duration_ms):
    offset, duration = raw.get("Offset"), raw.get("Duration")
    if offset is None and duration is None:
        return None, None
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (offset, duration)):
        raise ValueError("Invalid provider timing")
    # Azure word/phoneme offsets are already absolute within this input stream.
    start, end = offset // 10000, (offset + duration) // 10000
    if end > duration_ms:
        raise ValueError("Provider timing exceeds source")
    return start, end


def azure_analysis_identity(settings) -> SpeechAnalysisIdentity:
    """Public cache identity; no SDK/native import and no credential values."""
    key = settings.speaking_azure_key
    key = key.get_secret_value() if hasattr(key, "get_secret_value") else key
    configuration = {
        "resource_binding": _hash([key, settings.speaking_azure_region]),
        "billing_policy_version": "azure-billing-v1",
        "billing_mode": getattr(settings, "speaking_azure_billing_mode", "unknown"),
        "allow_paid": getattr(settings, "speaking_azure_allow_paid", False),
        "region": settings.speaking_azure_region,
        "locale": settings.speaking_azure_locale,
        "prosody_requested": settings.speaking_azure_prosody,
        "reference_text": "",
        "miscue": False,
        "granularity": "Phoneme",
        "output": "Detailed",
    }
    try:
        sdk_version = importlib.metadata.version("azure-cognitiveservices-speech")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = None
    return SpeechAnalysisIdentity(
        provider="azure-speech",
        adapter_version=ADAPTER_VERSION,
        sdk_version=sdk_version,
        locale=settings.speaking_azure_locale,
        configuration=configuration,
        configuration_fingerprint=_hash([ADAPTER_VERSION, sdk_version, configuration]),
    )


def _read_pcm(audio):
    """Finish all file access before SDK work; cancellation can safely release the file."""
    if not 0 <= audio.duration_ms <= 1800000:
        raise ValueError("Invalid normalized duration")
    with wave.open(str(audio.path), "rb") as wav:
        if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth(), wav.getcomptype()) != (
            1,
            16000,
            2,
            "NONE",
        ):
            raise ValueError("Invalid normalized WAV")
        frames = wav.getnframes()
        if frames * 1000 // 16000 != audio.duration_ms:
            raise ValueError("Normalized duration mismatch")
        pcm = wav.readframes(frames)
        if len(pcm) != frames * 2:
            raise ValueError("Incomplete normalized WAV")
        return pcm


class AzureSpeechAnalyzer:
    def __init__(self, settings):
        self.settings = copy.deepcopy(settings)
        concurrency, queue = (
            settings.speaking_azure_max_concurrency,
            settings.speaking_azure_max_queue,
        )
        if not 1 <= concurrency <= 32 or not 0 <= queue <= 256:
            raise ValueError("Invalid Azure speech capacity")
        if not 0 < settings.speaking_azure_timeout_seconds <= 3600:
            raise ValueError("Invalid Azure speech timeout")
        self._pool = _pool(concurrency, queue)
        self.identity = azure_analysis_identity(settings)

    def _empty(self, audio, response_id, take_number, segment_id):
        locale_ok = self.settings.speaking_azure_locale == "en-US"
        return SpeechAnalysisResult(
            provider=self.identity,
            source=SpeechAnalysisSource(
                audio_fingerprint=audio.source_audio_fingerprint,
                normalized_audio_fingerprint=audio.cache_key,
                duration_ms=audio.duration_ms,
                response_id=str(response_id) if response_id is not None else None,
                take_number=take_number,
                segment_id=str(segment_id) if segment_id is not None else None,
            ),
            status="FAILED",
            coverage=SpeechCoverage(audio_duration_ms=audio.duration_ms),
            capabilities=SpeechCapabilities(
                prosody_requested=self.settings.speaking_azure_prosody,
                prosody_supported=None if locale_ok else False,
            ),
            limitations=[
                "UNSCRIPTED_ASR_MAY_NORMALIZE_DISFLUENCIES",
                "SERVICE_MODEL_VERSION_UNKNOWN",
                "PROVIDER_SCORES_ARE_NOT_IELTS_BANDS",
                "BILLING_NOT_CONFIRMED",
            ]
            + (
                ["PROSODY_LOCALE_UNSUPPORTED"]
                if self.settings.speaking_azure_prosody and not locale_ok
                else []
            ),
        )

    async def analyze(
        self, audio: NormalizedAudio, *, response_id=None, take_number=None, segment_id=None
    ) -> SpeechAnalysisResult:
        started = time.monotonic()
        if (
            not isinstance(audio, NormalizedAudio)
            or audio.channels != 1
            or audio.sample_rate != 16000
            or audio.segment_count != 1
        ):
            raise ValueError("One continuous mono 16kHz normalized segment is required")
        result = self._empty(audio, response_id, take_number, segment_id)
        if not billing_authorized(self.settings):
            result.error_code = BILLING_BLOCKED
            result.usage.billing_uncertain = False
            result.latency_ms = 0
            return result
        if not self._pool.admission.acquire(blocking=False):
            return result.model_copy(
                update={"error_code": "AZURE_CAPACITY_EXCEEDED", "latency_ms": 0}
            )
        try:
            pcm = await await_audio_thread(asyncio.to_thread(_read_pcm, audio))
            result.source.normalized_audio_fingerprint = hashlib.sha256(pcm).hexdigest()
        except BaseException:
            self._pool.admission.release()
            raise
        cancel = threading.Event()
        gate = threading.Lock()

        def execute():
            try:
                return self._analyze_native(audio, pcm, result, cancel, gate)
            finally:
                self._pool.admission.release()

        future = asyncio.wrap_future(self._pool.executor.submit(execute))
        # Retrieve eventual failures even if the async caller already timed out/canceled.
        future.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        try:
            output = await asyncio.wait_for(
                asyncio.shield(future),
                self.settings.speaking_azure_timeout_seconds + CLEANUP_GRACE_SECONDS,
            )
            output.latency_ms = int((time.monotonic() - started) * 1000)
            return output
        except TimeoutError:
            cancel.set()
            with gate:
                snapshot = result.model_copy(deep=True)
            snapshot.limitations.append("NATIVE_CLEANUP_PENDING_CAPACITY_RETAINED")
            snapshot.latency_ms = int((time.monotonic() - started) * 1000)
            return self._finish(audio, snapshot, "AZURE_TIMEOUT", False)
        except asyncio.CancelledError:
            cancel.set()
            # Native worker owns PCM bytes, so a stalled stop cannot retain a caller's file.
            try:
                await asyncio.wait_for(asyncio.shield(future), CLEANUP_GRACE_SECONDS)
            except TimeoutError:
                pass
            raise

    def _analyze_native(self, audio, pcm, result, cancel, gate):
        if not billing_authorized(self.settings):
            result.error_code = BILLING_BLOCKED
            result.usage.billing_uncertain = False
            return result
        if cancel.is_set():
            return result.model_copy(
                update={"status": "CANCELLED", "error_code": "AZURE_CANCELLED"}
            )
        recognizer = None
        done = threading.Event()
        stream = None
        stream_closed = False
        accepting = True
        seen = set()
        error = None
        completed = False
        try:
            if not self.settings.speaking_azure_key or not self.settings.speaking_azure_region:
                raise ValueError("Missing Azure configuration")
            sdk = _load_sdk()
            key = self.settings.speaking_azure_key
            if hasattr(key, "get_secret_value"):
                key = key.get_secret_value()
            speech_config = sdk.SpeechConfig(
                subscription=key, region=self.settings.speaking_azure_region
            )
            speech_config.output_format = sdk.OutputFormat.Detailed
            speech_config.request_word_level_timestamps()
            stream = sdk.audio.PushAudioInputStream(
                sdk.audio.AudioStreamFormat(
                    samples_per_second=16000, bits_per_sample=16, channels=1
                )
            )
            audio_config = sdk.audio.AudioConfig(stream=stream)
            pronunciation = sdk.PronunciationAssessmentConfig(
                reference_text="",
                grading_system=sdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=sdk.PronunciationAssessmentGranularity.Phoneme,
                enable_miscue=False,
            )
            if (
                self.settings.speaking_azure_prosody
                and self.settings.speaking_azure_locale == "en-US"
            ):
                pronunciation.enable_prosody_assessment()
            recognizer = sdk.SpeechRecognizer(
                speech_config=speech_config,
                language=self.settings.speaking_azure_locale,
                audio_config=audio_config,
            )
            pronunciation.apply_to(recognizer)

            def recognized(event):
                nonlocal error
                with gate:
                    if not accepting or cancel.is_set():
                        return
                    if event.result.reason == getattr(sdk.ResultReason, "NoMatch", object()):
                        error = "AZURE_NO_MATCH"
                        start = end = None
                        try:
                            raw = json.loads(
                                event.result.properties.get(
                                    sdk.PropertyId.SpeechServiceResponse_JsonResult
                                )
                            )
                            start, end = _span(raw, audio.duration_ms)
                        except (ValueError, TypeError, AttributeError):
                            pass
                        result.uncertain_regions.append(
                            SpeechUncertainty(
                                evidence_id="uncertain_"
                                + _hash(
                                    [
                                        result.source.model_dump(),
                                        start,
                                        end,
                                        len(result.uncertain_regions),
                                    ]
                                )[:24],
                                start_ms=start,
                                end_ms=end,
                                reason="RECOGNITION_NO_MATCH",
                            )
                        )
                        return
                    if event.result.reason != sdk.ResultReason.RecognizedSpeech:
                        return
                    try:
                        raw = json.loads(
                            event.result.properties.get(
                                sdk.PropertyId.SpeechServiceResponse_JsonResult
                            )
                        )
                        if raw.get("RecognitionStatus") not in ("Success", 0):
                            return
                        identity = (
                            raw.get("Offset"),
                            raw.get("Duration"),
                            raw["NBest"][0].get("Lexical"),
                            event.result.result_id if raw.get("Offset") is None else None,
                        )
                        if identity in seen:
                            return
                        self._append_final(result, raw)
                        seen.add(identity)
                    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                        error = "AZURE_RESULT_INVALID"

            def stopped(_event):
                nonlocal completed
                with gate:
                    if accepting:
                        completed = True
                        done.set()

            def canceled(event):
                nonlocal error, completed, accepting
                with gate:
                    if accepting:
                        if event.reason == sdk.CancellationReason.EndOfStream:
                            completed = True
                        else:
                            codes = getattr(sdk, "CancellationErrorCode", None)
                            code = getattr(event, "error_code", None)
                            reason = quota_reason(
                                event,
                                sdk_code=code,
                                too_many_requests=getattr(codes, "TooManyRequests", None),
                            )
                            if reason:
                                error = QUOTA_EXCEEDED
                                result.provider_reason_code = reason
                            elif codes is not None and code == getattr(
                                codes, "AuthenticationFailure", object()
                            ):
                                error = AUTHENTICATION_FAILED
                            else:
                                error = "AZURE_SERVICE_ERROR"
                            accepting = (
                                False  # Fence fatal errors before native stop/late callbacks.
                            )
                        done.set()

            recognizer.recognized.connect(recognized)
            recognizer.session_stopped.connect(stopped)
            recognizer.canceled.connect(canceled)
            result.usage = SpeechUsage(
                attempted_calls=1, submitted_audio_ms=audio.duration_ms, outcome="UNKNOWN"
            )
            deadline = time.monotonic() + self.settings.speaking_azure_timeout_seconds
            # Do not block on startup future: canceled/session events report service errors.
            _start_future = recognizer.start_continuous_recognition_async()
            stream.write(pcm)
            stream.close()
            stream_closed = True
            while not done.wait(0.01):
                if cancel.is_set():
                    error = "AZURE_CANCELLED"
                    break
                if time.monotonic() >= deadline:
                    error = "AZURE_TIMEOUT"
                    break
        except (
            ImportError,
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
        ) as failure:
            if error not in {QUOTA_EXCEEDED, AUTHENTICATION_FAILED}:
                reason = quota_reason(failure)
                error = QUOTA_EXCEEDED if reason else "AZURE_UNAVAILABLE"
                result.provider_reason_code = reason
        finally:
            with gate:
                accepting = False  # Fence before stop: late callbacks cannot mutate the result.
            if stream is not None and not stream_closed:
                try:
                    stream.close()
                except Exception:
                    error = error or "AZURE_CLEANUP_FAILED"
            if recognizer is not None:
                try:
                    recognizer.stop_continuous_recognition_async().get()
                except Exception:
                    error = error or "AZURE_CLEANUP_FAILED"
                for signal in (
                    recognizer.recognized,
                    recognizer.session_stopped,
                    recognizer.canceled,
                ):
                    try:
                        signal.disconnect_all()
                    except Exception:
                        error = error or "AZURE_CLEANUP_FAILED"
        with gate:
            return self._finish(audio, result, error, completed)

    def _finish(self, audio, result, error, completed):
        result.utterances.sort(key=lambda item: item.start_ms if item.start_ms is not None else -1)
        result.words.sort(key=lambda item: item.start_ms if item.start_ms is not None else -1)
        result.lexical_transcript = " ".join(u.lexical_text for u in result.utterances)
        result.display_transcript = (
            " ".join(u.display_text for u in result.utterances)
            if result.utterances and all(u.display_text is not None for u in result.utterances)
            else None
        )
        result.coverage = SpeechCoverage(
            audio_duration_ms=audio.duration_ms,
            stream_completed=completed and error is None,
            final_utterance_count=len(result.utterances),
            word_count=len(result.words),
            timed_word_count=sum(w.start_ms is not None for w in result.words),
            confidence_word_count=sum(w.recognition_confidence is not None for w in result.words),
            recognized_span_ms=sum(
                u.end_ms - u.start_ms for u in result.utterances if u.start_ms is not None
            ),
        )
        caps = result.capabilities
        caps.word_timing_observed = (
            True if any(w.start_ms is not None for w in result.words) else None
        )
        caps.recognition_confidence_observed = (
            True
            if any(
                w.recognition_confidence is not None for w in [*result.words, *result.utterances]
            )
            else None
        )
        caps.pronunciation_observed = (
            True if any(o.kind == "pronunciation" for o in result.observations) else None
        )
        caps.phonemes_observed = (
            True if any(o.kind == "phoneme" for o in result.observations) else None
        )
        caps.prosody_observed = (
            True if any(o.kind == "prosody" for o in result.observations) else None
        )
        if caps.prosody_observed:
            caps.prosody_supported = True
        if completed and not result.utterances and error is None:
            error = "AZURE_NO_MATCH"
        result.error_code = error
        if error == "AZURE_CANCELLED":
            result.status = "CANCELLED"
        elif error or not completed:
            result.status = "PARTIAL" if result.utterances else "FAILED"
        else:
            result.status = "COMPLETE"
        if not result.words:
            result.limitations.append("WORD_EVIDENCE_UNAVAILABLE")
        if result.usage.attempted_calls:
            result.usage.outcome = "COMPLETED" if result.status == "COMPLETE" else result.status
            result.usage.successful_calls = int(result.status == "COMPLETE")
            result.usage.failed_calls = int(result.status in ("FAILED", "PARTIAL"))
        return SpeechAnalysisResult.model_validate(result.model_dump())

    def _append_final(self, result, raw):
        """Parse into local lists first: malformed finals cannot leave half an utterance."""
        best = raw["NBest"][0]
        text = best.get("Lexical")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Missing lexical transcript")
        start, end = _span(raw, result.source.duration_ms)
        seed = [
            result.source.model_dump(),
            result.provider.configuration_fingerprint,
            raw.get("Offset"),
            text,
            len(result.utterances) if raw.get("Offset") is None else None,
        ]
        uid = "utt_" + _hash(seed)[:24]
        display = best.get("Display", raw.get("DisplayText"))
        utterance = SpeechUtterance(
            evidence_id=uid,
            start_ms=start,
            end_ms=end,
            lexical_text=text,
            display_text=display,
            recognition_confidence=_number(best.get("Confidence"), 1),
        )
        observations, words = [], []

        def observe(item, target, bounds, token=None, kind="pronunciation"):
            assessment = item.get("PronunciationAssessment") or {}
            for metric in ("AccuracyScore", "PronScore", "FluencyScore", "ProsodyScore"):
                value = _number(assessment.get(metric), 100)
                if value is not None:
                    observed_kind = (
                        "prosody"
                        if metric == "ProsodyScore"
                        else "fluency"
                        if metric == "FluencyScore"
                        else kind
                    )
                    observations.append(
                        SpeechObservation(
                            evidence_id="obs_" + _hash([target, metric, kind])[:24],
                            target_id=target,
                            start_ms=bounds[0],
                            end_ms=bounds[1],
                            kind=observed_kind,
                            metric=metric,
                            score=value,
                            token=token,
                            source="azure-pronunciation-assessment",
                            certainty="provider_measurement",
                            limitations=["PROVIDER_SCORES_ARE_NOT_IELTS_BANDS"]
                            + (
                                ["LOW_ACCURACY_DOES_NOT_IDENTIFY_SUBSTITUTION"]
                                if metric == "AccuracyScore"
                                else []
                            ),
                        )
                    )
            labels = [assessment.get("ErrorType")]
            feedback = assessment.get("Feedback") or {}
            for family in ("Break", "Intonation"):
                details = feedback.get(family) or {}
                labels.extend(details.get("ErrorTypes") or [])
                for measure in ("UnexpectedBreak", "MissingBreak", "Monotone"):
                    name = "SyllablePitchDeltaConfidence" if measure == "Monotone" else "Confidence"
                    confidence = _number((details.get(measure) or {}).get(name), 1)
                    if confidence is None:
                        continue
                    measure_target = uid if measure == "Monotone" else target
                    oid = "obs_" + _hash([measure_target, measure, name])[:24]
                    if any(o.evidence_id == oid for o in observations):
                        continue
                    measure_bounds = (start, end) if measure == "Monotone" else bounds
                    observations.append(
                        SpeechObservation(
                            evidence_id=oid,
                            target_id=measure_target,
                            start_ms=measure_bounds[0],
                            end_ms=measure_bounds[1],
                            kind="prosody",
                            metric=f"{measure}.{name}",
                            provider_confidence=confidence,
                            source="azure-pronunciation-assessment",
                            certainty="provider_measurement",
                            limitations=["NO_CALIBRATED_ERROR_THRESHOLD_APPLIED"],
                        )
                    )
            for label in labels:
                if not isinstance(label, str) or label in ("None", "Omission", "Insertion"):
                    continue
                if label == "Monotone" and any(o.label == label for o in observations):
                    continue
                # Monotone is utterance-level feedback repeated on words by the provider.
                label_target = uid if label == "Monotone" else target
                label_bounds = (start, end) if label == "Monotone" else bounds
                label_id = "obs_" + _hash([label_target, "error", label])[:24]
                if any(o.evidence_id == label_id for o in observations):
                    continue
                observations.append(
                    SpeechObservation(
                        evidence_id=label_id,
                        target_id=label_target,
                        start_ms=label_bounds[0],
                        end_ms=label_bounds[1],
                        kind="prosody"
                        if label in ("UnexpectedBreak", "MissingBreak", "Monotone")
                        else kind,
                        metric="error_type",
                        label=label,
                        token=None if label == "Monotone" else token,
                        source="azure-pronunciation-assessment",
                        certainty="provider_flag",
                        limitations=["PROVIDER_ERROR_LABEL_REQUIRES_REVIEW"],
                    )
                )

        observe(best, uid, (start, end))
        for index, word in enumerate(best.get("Words") or []):
            bounds = _span(word, result.source.duration_ms)
            wid = "word_" + _hash([uid, index, word.get("Word")])[:24]
            words.append(
                SpeechWord(
                    evidence_id=wid,
                    utterance_id=uid,
                    text=word["Word"],
                    start_ms=bounds[0],
                    end_ms=bounds[1],
                    recognition_confidence=_number(word.get("Confidence"), 1),
                )
            )
            observe(word, wid, bounds, word["Word"])
            for group, kind, token_key in (
                ("Phonemes", "phoneme", "Phoneme"),
                ("Syllables", "syllable", "Syllable"),
            ):
                for position, unit in enumerate(word.get(group) or []):
                    target = "unit_" + _hash([wid, kind, position])[:24]
                    observe(
                        unit,
                        target,
                        _span(unit, result.source.duration_ms),
                        unit.get(token_key),
                        kind,
                    )
        result.utterances.append(utterance)
        result.words.extend(words)
        result.observations.extend(observations)
