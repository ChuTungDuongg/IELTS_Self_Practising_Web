# Speaking evaluation inputs

For private MP3/WAV replay without a production attempt or compulsory human labels,
see [the audio replay guide](../../docs/testing/speaking-audio-replay.md).
Place recordings in `private/replay/`; generated output goes to `reports/replay/`.
Both directories, including audio, transcripts, labels and checkpoints, are gitignored.
Run prepare/validate offline first. Live calls require explicit flags and an operator cost estimate.

The strict labelled dataset workflow remains in `scripts/evaluate_speaking.py` and
[AI Speaking](../../docs/ai-speaking.md). Replay success is not IELTS accuracy validation.
