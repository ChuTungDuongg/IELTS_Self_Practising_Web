# Speaking architecture and evaluation

Speaking P1–P8 is implemented. All AI bands and feedback are advisory: this
project has no benchmark evidence establishing examiner-equivalent accuracy.
P8 adds an evaluation harness; it does not change production scores or schema.

## Runtime and grading

Next.js supplies authored prompts, microphone preflight, recording and review.
FastAPI owns prompt transitions, timestamps/deadlines, retry restrictions and
private media authorization. PostgreSQL stores frozen test versions and attempt
provenance; audio containers live in private storage. Chunk uploads are
idempotent. Reload recovery preserves server remaining time and grants one
seven-second recovery grace without increasing the speaking quota. A recovered
recorder creates a separate container segment. Final upload acknowledgements
precede advancement. Scratch notes stay outside spoken-response grading inputs.

The pipeline is committed raw audio → normalized mono 16 kHz PCM → quality gate
→ verbatim ASR with word timing → clean formatting and versioned fluency/acoustic
features → holistic FC/LR/GRA/PR assessment. Recovery containers are decoded
separately before combining PCM. Clean text preserves candidate words and grammar.
On Modal, Web runs FFmpeg, quality, fluency and pronunciation evidence on CPU;
only the normalized WAV travels from FastAPI to a separate, proxy-protected
faster-whisper T4 service. Its pinned large-v3 model cache is on
`ielts-speaking-asr-model-cache`; request audio uses disposable private temp
files outside that Volume. The existing Ministral L4 service serves both Writing
and Speaking criterion scoring. Both GPU services have zero minimum containers,
so a Web startup alone does not load either model. A first transcription can
incur model download/load and queueing; do not infer steady-state latency from it.
Timing-derived features describe speech; they do not mechanically assign bands.
Pronunciation needs measured audio evidence and cannot succeed from transcript
text or ASR confidence alone. Unassessable audio or insufficient pronunciation
evidence produces an unavailable criterion, not an invented zero or average.

`SpeakingScorer` validates a half-band score first, persists it through a
checkpoint, and then requests bounded feedback. Feedback failure keeps the valid
score. The production overall uses equal FC/LR/GRA/PR weights and the project's
half-band rounding; any missing criterion leaves overall unavailable. Durable
workers and events support cancellation, reconnect and restart. Speaking joins
Full Mock, history and classroom results. Teachers get read-only access only
through assignment provenance; unrelated personal attempts remain private.

## Private benchmark inputs

The harness follows the existing `app/evaluation` and root `scripts` conventions.
Use a UTF-8 JSONL manifest, one whole labelled performance per line:

```json
{"schema_version":1,"id":"synthetic-001","responses":[{"audio_path":"audio/fictional.wav","part_number":1,"prompt_type":"SHORT_ANSWER","prompt_text":"Describe a fictional garden."}],"human":{"fc":6,"lr":6.5,"gra":7,"pr":6.5,"overall":6.5},"subgroups":{"recording_environment":"quiet"},"assessor_version":"fictional-rater-v1"}
```

This example is fictional, not human assessment evidence. Each response requires
exactly one `audio_path` or controlled `fixture_id`; paths resolve beside the
manifest and may point to private files outside git. Fixture IDs are for injected
offline test loaders; the real audio loader fails closed on them. Prompts are
required to reproduce contextual assessment. Optional `test_reference` is an
opaque identifier. Assessor metadata is only a non-identifying version token.
All five human labels are required finite numbers in 0–9 at half-band increments;
human overall is an independent label and is not recomputed from its criteria.
Unknown fields, duplicate IDs/JSON keys and sensitive subgroup keys are rejected.
Inputs are capped at 16 MiB and 10,000 samples; validation examines all rows even
when `--max-samples` limits evaluation to the first N.

Keep candidate audio, manifests, private dotenv configuration and result files
outside git or under ignored `benchmarks/speaking/private/` and
`benchmarks/speaking/reports/`. Obtain permission and check licenses before
processing speech with any external provider. Do not commit copyrighted tests,
private recordings or identifying transcripts. Git ignores are an additional
guard, not permission to redistribute data elsewhere.

## Offline workflow

From `backend/`, manifest validation never constructs a provider:

```powershell
uv run python ../scripts/evaluate_speaking.py --manifest ../benchmarks/speaking/private/manifest.jsonl --validate-manifest
```

For offline reports, import score-only results from an existing scorer run:

```powershell
uv run python ../scripts/evaluate_speaking.py --manifest ../benchmarks/speaking/private/manifest.jsonl --predictions ../benchmarks/speaking/private/predictions.json --output ../benchmarks/speaking/reports/offline
```

Prediction JSON has `schema_version: 1`, a required `provenance` object (the
`ScorerProvenance` contract) and `predictions`, each containing `id`, `scores`
with FC/LR/GRA/PR half-bands or null, and optional allowlisted `reasons`.
Do not supply overall: the harness calls production `speaking_overall`. Missing
samples or criteria remain failures in denominators. Unknown sample IDs, arbitrary
error text, transcripts and extra fields are rejected. Imported provider metadata
is an assertion by the result author, not proof that the provider was invoked.

For a synthetic-only offline smoke, generate files with this Python snippet from
`backend/`, then run the two commands above:

```python
import json
from pathlib import Path
from app.core.config import Settings
from app.evaluation.speaking.models import provenance

root = Path("../benchmarks/speaking/private")
root.mkdir(parents=True, exist_ok=True)
sample = {"schema_version": 1, "id": "synthetic-001", "responses": [
    {"fixture_id": "fictional-tone", "part_number": 1,
     "prompt_type": "SHORT_ANSWER", "prompt_text": "Describe a fictional garden."}],
    "human": {"fc": 6, "lr": 6.5, "gra": 7, "pr": 6.5, "overall": 6.5}}
identity = provenance(Settings()).model_copy(update={
    "provider": "fixture", "model": "synthetic-v1",
    "asr_provider": "fixture", "asr_model": "synthetic-v1"})
(root / "manifest.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
(root / "predictions.json").write_text(json.dumps({"schema_version": 1,
    "provenance": identity.model_dump(mode="json"), "predictions": [
        {"id": sample["id"], "scores": {"fc": 6, "lr": 6, "gra": 6, "pr": 6}}]}),
    encoding="utf-8")
```

Synthetic predictions exercise arithmetic and file contracts; they cannot measure
real scorer accuracy. Automated tests use synthetic evidence and fake providers:

```powershell
uv run pytest tests/test_speaking_benchmark.py tests/test_speaking_benchmark_metrics.py -q
```

## Manual configured scoring

Live scoring requires explicit `--allow-live`. The CLI reads the same backend
`Settings` as production; `--config` selects a private dotenv file without putting
secrets in command arguments. For local ASR, set `SPEAKING_ASR_PROVIDER=local`,
install the optional `backend[speech]` extra, and point
`SPEAKING_ASR_MODEL_DIRECTORY` at a complete local model. For Modal ASR, set
`SPEAKING_ASR_PROVIDER=modal`, `SPEAKING_ASR_ENABLED=true`, the protected
`SPEAKING_ASR_BASE_URL`, pinned `SPEAKING_ASR_MODEL`,
`SPEAKING_ASR_MODEL_REVISION` and `SPEAKING_ASR_VERSION`, plus backend-only
`AI_WRITING_MODAL_KEY`/`AI_WRITING_MODAL_SECRET`. Production Web hydrates these
settings automatically; local manual evaluation needs private configuration.
Enable the existing Speaking LLM transport and pronunciation provider separately.
No dataset/model downloader is added to the benchmark workflow.

```powershell
uv run python ../scripts/evaluate_speaking.py --manifest ../benchmarks/speaking/private/manifest.jsonl --allow-live --config ../benchmarks/speaking/private/providers.env --output ../benchmarks/speaking/reports/candidate --resume
```

The adapter calls existing normalizer, quality, ASR, feature and `SpeakingScorer`
contracts, not a second grader. WAV inputs must already be mono 16 kHz signed
16-bit PCM; WebM/Ogg/MP4/M4A use the production bounded FFmpeg decoder. One file
represents one complete response container. Supply immutable inputs; conversion
uses temporary private artifacts. Unsupported, missing or oversized raw files
(128 MiB limit), quality failures and provider failures produce safe failure
codes. No production attempt or score row is modified.

`predictions.json` is atomically checkpointed before each feedback request. Resume
reuses only fully scored samples matching the exact sample, audio content hash,
configuration and provenance; failed/partial samples are retried. It is a
sequential local workflow: do not run multiple writers into one output directory.
Feedback failures do not count as nonscorable if the criterion score was saved.
Provider failures remain visible in the final failure rate; CLI exit 0 means the
report was produced, not that all samples were scorable. Invalid input/I/O failures
return exit 2 with bounded error codes. Routine tests never invoke live ASR/LLM,
Modal or GPU services.

## Reports and metrics

Outputs are deterministic `summary.json`, `summary.md`, `samples.csv` and
`samples.jsonl`, plus score checkpoints for configured scoring. Reports contain
sample IDs, bands, signed errors and safe reason codes, not audio bodies,
transcripts, prompts, filesystem paths, hidden reasoning or provider messages.
Summary includes largest disagreements, signed error distributions and descriptive
human-band calibration buckets. These buckets apply no score correction.

All five criteria have total/valid counts, coverage and nonscorable/failure rate.
MAE is mean absolute predicted-minus-human error; RMSE is its root mean square.
Pearson measures linear association; Spearman uses average ranks for ties.
Quadratic Weighted Kappa compares observed versus marginal expected squared
category disagreement over the 19 project half-band bins from 0 to 9. Within
±0.5/±1.0 and exact agreement are fractions of valid pairs. Correlation is not
agreement: a shifted scorer can correlate well while having substantial MAE.

Paired statistics exclude missing predictions but failures always remain in
coverage denominators. Correlation requires at least three valid pairs; QWK five.
Too few pairs, constant vectors and zero expected kappa disagreement yield null
with an explanatory status, never NaN. All-failed cohorts still produce reports.
Subgroups are optional recording environment, proficiency bucket, prompt group
or microphone category. Default minimum is 20 labelled samples per slice;
`--minimum-subgroup-samples` is configurable with a floor of five. Small slices
are suppressed; remaining paired statistics still enforce their own sample
limits. No sensitive demographic analysis or small-sample fairness claim is made.

Every result records scorer/provider/model, rubric/prompt, score/feedback contracts,
ASR provider/model/version and alignment, normalizer, quality, fluency and
pronunciation versions, configuration/implementation hashes and git SHA when
available. Secrets and model directory paths are hashed, not emitted. Model
weights and deployment behavior must be pinned and their declared versions
updated when changed; a model name alone does not identify mutable weights.
Use the same cohort hash, labels and metric protocol when comparing runs, and
examine failure-rate changes alongside agreement. No automatic promotion occurs.

## Research data and calibration policy

[Speak & Improve Corpus 2025](https://researchdatasets.cambridge.org/datasets/speak-and-improve-corpus-2025)
contains indicative holistic CEFR labels. Its publisher restricts redistribution
and use, including non-commercial research/education licensing and approval for
releasing derived material; check its terms and provider retention policy first.
[SpeechOcean762](https://github.com/jimbozhang/speechocean762) targets pronunciation
assessment. [L2-ARCTIC](https://psi.engr.tamu.edu/l2-arctic-corpus-docs/) supports
research on non-native speech and pronunciation. These and other pronunciation
corpora can support auxiliary validation; none automatically supplies official
IELTS FC/LR/GRA/PR ground truth. Review each dataset's current license, consent and
permitted use separately. No downloads or recordings are bundled here.

Do not map a SpeechOcean score or ASR confidence directly to IELTS Pronunciation
or overall. Build a representative, independently labelled performance benchmark
with assessor agreement and held-out evaluation before making accuracy claims.
Use results to identify bias, compare versions, detect regressions and decide
whether calibration is needed. A small run does not justify production offsets.
Any future transformation must be explicit, versioned, separately reviewed and
validated on held-out data. P8 contains no hidden calibration or score manipulation.
