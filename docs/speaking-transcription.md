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

Word timings must be finite, nonnegative, ordered and nonoverlapping, with ends bounded by decoded duration. Invalid or overlapping provider metadata fails the response safely rather than becoming timing evidence. Cached WAV headers/body/duration are verified before reuse; missing or corrupt derivatives are rebuilt and old paths enter the cleanup outbox. Raw missing/corrupt/traversing inputs fail closed. Historical transcripts are hidden when their audio fingerprint no longer matches the committed response.
