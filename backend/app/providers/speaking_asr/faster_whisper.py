"""Optional local-only adapter. Importing the app never loads speech packages."""

import asyncio
import logging
from pathlib import Path

from app.core.exceptions import AppError
from app.providers.speaking_asr import provider_identity
from app.providers.speaking_asr.base import ASRResult, WordTiming
from app.services.speaking_audio import NormalizedAudio


class FasterWhisperProvider:
    def __init__(self, settings):
        self.settings = settings
        self.identity = provider_identity(settings)
        self._model = None

    async def transcribe(self, audio: NormalizedAudio) -> ASRResult:
        if (
            not isinstance(audio, NormalizedAudio)
            or audio.channels != 1
            or audio.sample_rate != 16000
        ):
            raise AppError("SPEAKING_AUDIO_UNASSESSABLE", "Normalized audio is required.", 409)
        return await asyncio.to_thread(self._transcribe, audio)

    def _transcribe(self, audio):
        try:
            directory = Path(self.settings.speaking_asr_model_directory)
            if not directory.is_dir():
                raise ValueError("Model unavailable")
            # The upstream constructor can fetch a tokenizer when it is absent,
            # even with local_files_only. Require a complete local model first.
            if not all(
                (directory / name).is_file()
                for name in (
                    "model.bin",
                    "config.json",
                    "tokenizer.json",
                    "preprocessor_config.json",
                )
            ):
                raise ValueError("Local model is incomplete")
            if self._model is None:
                logging.getLogger("faster_whisper").disabled = True
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    str(directory), device="cpu", compute_type="int8", local_files_only=True
                )
            segments, info = self._model.transcribe(
                str(audio.path),
                language=self.settings.speaking_asr_language,
                word_timestamps=True,
                vad_filter=True,
            )
            text, words = [], []
            for segment in segments:
                text.append(segment.text)
                words.extend(
                    WordTiming(word=w.word, start=w.start, end=w.end, confidence=w.probability)
                    for w in (segment.words or [])
                )
            return ASRResult(
                text="".join(text),
                words=words,
                provider=self.identity["provider"],
                model=self.identity["model"],
                version=self.identity["version"],
                language=info.language,
            )
        except (ImportError, OSError, ValueError):
            raise AppError(
                "SPEAKING_ASR_UNAVAILABLE", "Local transcription is unavailable.", 503
            ) from None
