# Azure speech analysis boundary

Implementation status: **LIVE_UNVERIFIED**. Offline tests exercise SDK events, not a paid
Azure resource. No live audio was submitted and no provider was enabled or deployed.

The optional `azure-speech` extra pins `azure-cognitiveservices-speech==1.53.0`, verified
against [PyPI release metadata](https://pypi.org/project/azure-cognitiveservices-speech/1.53.0/).
Native Linux dependencies and supported operating systems must follow Microsoft's
[SDK platform setup](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/quickstarts/setup-platform).
The SDK package version identifies the client; it does not identify the hosted service
model. Service model version remains unknown unless an explicit service field is supported.

## Provider behavior

`AzureSpeechAnalyzer(settings).analyze(...)` accepts one continuous, normalized mono 16 kHz
PCM WAV. The parent coordinator owns recovered-segment splitting and rebasing. The adapter
finishes reading the WAV before native recognition and feeds owned PCM bytes through a push
stream. Neither the SDK nor stalled cleanup retains the caller's file.

The configuration requests continuous recognition, detailed output and word timestamps.
Pronunciation assessment uses empty reference text, phoneme granularity and disabled miscues;
exam prompts and cue cards never become reference text. Optional prosody is requested only
for en-US. Observed support remains unknown until actual evidence arrives. Numeric provider
measurements and flags remain advisory; no completeness penalty or IELTS conversion is applied.
The provider's [pronunciation assessment documentation](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-pronunciation-assessment)
describes the configuration, locale restriction and pronunciation-specific recognition model.
The [portal guide](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/pronunciation-assessment-tool)
distinguishes unscripted speaking from scripted reading.

Only final recognized events enter the result. Duplicate final deliveries are suppressed;
interim text cannot duplicate words. Timings convert absolute stream ticks into integer
milliseconds by dividing by 10,000, without adding the utterance offset again. Missing
timings, names, scores and recognition confidence stay unknown. `AccuracyScore` never becomes
ASR confidence. Lexical and display text remain separate, without grammar correction or
invented fillers. See Microsoft's [recognition results guide](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-speech-recognition-results)
and official [Python continuous-recognition sample](https://github.com/Azure-Samples/cognitive-services-speech-sdk/blob/master/samples/python/console/speech_sample.py).
The pronunciation example is now in the official repository's
[language-learning scenario](https://github.com/Azure-Samples/cognitive-services-speech-sdk/blob/master/scenarios/python/console/language-learning/pronunciation_assessment.py).

## Evidence and failure semantics

The private `speech-analysis.v1` contract carries source/normalized fingerprints, response,
take and segment identities, secret-free provider/config identity, utterances, words and
observations with stable evidence IDs. Every observation has provider provenance, categorical
certainty and limitations. A low accuracy measurement does not identify a substituted sound.
Phoneme names are retained only when present. Nested prosody break confidence remains a
provider measurement without an adapter-chosen error threshold. Repeated utterance-wide
Monotone flags collapse to one utterance observation.

`COMPLETE` requires a completed stream with at least one final utterance and no detected
failure. An interrupted stream with usable finals is `PARTIAL`; an empty/failed stream is
`FAILED`. Caller task cancellation propagates `CancelledError`; a canceled native result
can carry `CANCELLED`. Authentication, quota, timeout, malformed results and no-match have
bounded public error codes. Private service error descriptions and raw SDK JSON are neither
logged nor copied to the contract.

An in-process pool shares configured worker and queue limits across analyzer instances.
Admission rejection makes no provider call. Recognition has a deadline and a 250 ms native
cleanup grace period. SDK shutdown futures cannot be forcibly terminated safely: if native
cleanup stalls, the async caller receives a timeout snapshot, late callbacks are fenced and
the worker retains its slot. Further calls eventually reject instead of spawning unbounded
threads. A process restart may be needed for a permanently stalled SDK. Pool limits are
shared per configured `(max_concurrency, max_queue)` pair; runtime configuration must stay
consistent inside one process. Fleet concurrency still scales with the number of processes.

Usage records attempted calls, submitted duration, completed/failed outcomes and elapsed
latency, including partial and failed requests. The adapter never retries billable work.
Azure billing, service-internal retries, rounding and any prosody surcharge are not inferred:
`billed_duration_ms` remains unknown and `billing_uncertain` stays true, even after failure.
This is an observation ledger rather than an invoice or an exactly-once guarantee across
worker crashes. Durable checkpoints and retry authorization belong to the parent worker.

## Offline verification

The initial boundary test run failed before implementation. Targeted tests cover final-only
multi-utterance parsing, absolute ticks, optional values, separate confidence, deduplication,
malformed partial output, no-match, authentication/quota, timeout, cancellation, late callbacks,
bounded shared admission, stalled cleanup, provenance and secret handling. Fictional fixtures
contain no licensed exam content. Live model quality, accent fairness, billing, latency and
long-audio reliability still require the separately authorized evaluation protocol.
