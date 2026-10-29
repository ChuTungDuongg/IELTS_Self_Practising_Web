> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Speaking transcript processing extends the private P3 recording domain. It does not a. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/services/speaking_transcript_worker.py).
> Đọc cùng [current module/guide](modules/speaking.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Speaking transcript processing extends the private P3 recording domain. It does not assign IELTS scores.

The normalizer decodes each MediaRecorder container independently, concatenating chunks only inside that container. FFmpeg resamples each input before concatenating 16 kHz mono signed 16-bit PCM. Raw files are never rewritten. Input demuxers and protocols are restricted; commands use argument arrays, a timeout and output/duration limits. Subprocess output is discarded rather than logged. Derived files stay in `storage/speaking-derived` and are covered by the transactional deletion cleanup outbox.

Normalization cache identity includes the committed audio fingerprint, format, normalizer version and duration bound. Transcript identity additionally includes ASR provider/model/version/config and deterministic formatting version. A unique attempt/cache key and a parent attempt lock prevent duplicate jobs; a run lock and fenced lease protect worker checkpoints. Successful response transcripts survive other response failures and retries. Pending work is recovered on application restart; stale leases can be reclaimed. SSE observes persisted events and never owns or cancels the worker.

VERBATIM preserves provider text. CLEAN only collapses whitespace. It does not change grammar, vocabulary, tense, articles, fillers, repetitions or false starts. Only committed audio enters the provider; private runtime scratch notes never enter processing inputs. Word timings and text sizes are validated. Provider errors become allowlisted codes; event payloads contain status/response identifiers rather than transcript bodies. Owner authorization or existing assignment provenance is checked on every transcript read. Assignment teachers are read-only and cannot request generation.

Transcription defaults to disabled. Base dependencies and imports do not install or load speech models. The optional `speech` extra declares faster-whisper; it was not installed during development verification. To enable processing in a separately prepared local environment, configure:

```dotenv
SPEAKING_ASR_ENABLED=false
SPEAKING_ASR_MODEL_DIRECTORY=
SPEAKING_ASR_MODEL=local-model
SPEAKING_ASR_VERSION=faster-whisper-v1
SPEAKING_ASR_LANGUAGE=en
SPEAKING_NORMALIZER_VERSION=pcm-v1
SPEAKING_FFMPEG_PATH=ffmpeg
SPEAKING_PROCESSING_TIMEOUT_SECONDS=120
SPEAKING_MAX_DECODED_SECONDS=600
SPEAKING_TRANSCRIPT_STALE_SECONDS=300
```

Use a complete pre-existing converted model directory, including model.bin, config.json, tokenizer.json and preprocessor_config.json. The adapter rejects incomplete directories before importing the optional package and requests CPU/int8 with `local_files_only=True`. The explicit tokenizer check also blocks the upstream constructor's tokenizer fallback. See the [official faster-whisper constructor](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py). Bump model/adapter version when replacing local model contents. No cloud ASR is enabled.

Routine tests use synthetic bytes/WAV and fake ASR/subprocess adapters. They do not execute FFmpeg, download models, or perform live speech inference. Migration and PostgreSQL-backed tests must pass before the transcript phase is considered complete.

The quality gate runs before ASR and persists versioned evidence in the normalized artifact metadata. It distinguishes AUDIO_OK, NO_SPEECH, TOO_SHORT, AUDIO_CORRUPT, VERY_LOW_SIGNAL, SEVERE_CLIPPING, BACKGROUND_DOMINANT and ASR_UNUSABLE. `SPEAKING_QUALITY` accepts bounded JSON configuration overrides. Defaults use 20ms frame energy for activity and sustained high zero-crossing activity for a background-noise proxy. These are deterministic technical proxies, not a trained VAD or recognition of linguistic speech, and require calibration against representative recordings. Thresholds classify technical availability only; no IELTS score is produced. The quality configuration participates in transcript cache identity.

Decoded duration contains accepted audio only. Multi-container normalization records segment count; physical recovery gap boundaries are unavailable. The seven-second reconnect grace is never inserted into normalized audio or speech quota. Raw source and scratch notes remain outside the quality input contract.

Fluency evidence uses VERBATIM and exact token-aligned timings. WPM counts verbatim words over accepted decoded duration; articulation rate counts those words over summed aligned word durations. Incomplete/mismatched timings leave speech/silence/articulation/pause evidence unavailable. Pauses are inter-word gaps of at least 0.25s; long pauses are at least 2s, and long-pause ratio is the fraction of detected pauses that are long. Turns span words between long pauses, including shorter gaps. Part 2 sustained duration is the longest such turn for the authored LONG_TURN only. Recovery containers without trustworthy boundary offsets leave pause/turn evidence unavailable, while decoded duration excludes reconnect grace. Lexical um/uh, token/phrase repetitions, dash false starts and “I mean” are explicitly marked text proxies.

The replaceable pronunciation provider requires a real readable normalized WAV. Its lightweight baseline measures bounded 40ms pitch/autocorrelation and RMS/word-energy variation, plus alignment duration/gap/confidence summaries. Pitch is sampled deterministically from at most 128 active frames by default. ASR confidence is identified as an intelligibility proxy with explicit coverage; it is not a phonetic accuracy or IELTS score. Missing/low-confidence alignment returns LOW_EVIDENCE. A disabled provider or unusable audio returns UNAVAILABLE. Phoneme substitutions, linguistic stress and listener effort are explicitly null because the baseline cannot support those claims. These proxies need real-data calibration before stronger assessment claims.

`SPEAKING_PRONUNCIATION` accepts bounded JSON overrides; `SPEAKING_PRONUNCIATION_ENABLED=false` keeps transcription usable with explicit pronunciation unavailability. Provider and feature versions/config participate in run identity. Quality/fluency/pronunciation bundles are persisted atomically alongside each VERBATIM/CLEAN pair in private transcript provider metadata, with a fingerprint covering audio, transcript/alignment, quality, feature/provider config and long-turn context. Transcription itself does not score; the separate [advisory grading workflow](speaking-grading.md) consumes this evidence.

Word timings must be finite, nonnegative, ordered and nonoverlapping, with ends bounded by decoded duration. Invalid or overlapping provider metadata fails the response safely rather than becoming timing evidence. Cached WAV headers/body/duration are verified before reuse; missing or corrupt derivatives are rebuilt and old paths enter the cleanup outbox. Raw missing/corrupt/traversing inputs fail closed. Historical transcripts are hidden when their audio fingerprint no longer matches the committed response.
