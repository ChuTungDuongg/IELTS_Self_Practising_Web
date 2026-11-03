"""Shareable replay summaries exclude source names, prompts, transcripts and feedback text."""

import json

from app.evaluation.speaking.metrics import score_metrics
from app.evaluation.speaking.replay_cache import private_write

CRITERIA = ("fc", "lr", "gra", "pr")


def compare_labels(labels, scores, overall):
    if labels is None or not labels.provenance.verified:
        return {"status": "UNLABELLED" if labels is None else "LABELS_UNVERIFIED", "metrics": {}}
    published = labels.bands.model_dump(exclude_none=True)
    predictions = {**scores, "overall": overall}
    return {
        "status": "VERIFIED_HUMAN_LABELS",
        "human_bands": published,
        "provenance_kind": labels.provenance.kind,
        "metrics": {
            key: score_metrics([value], [predictions.get(key)]) for key, value in published.items()
        },
        "differences": {
            key: predictions[key] - value if predictions.get(key) is not None else None
            for key, value in published.items()
        },
    }


def write_replay_reports(output, report):
    output.mkdir(parents=True, exist_ok=True)

    def write(name, value):
        private_write(output / name, json.dumps(value, indent=2, allow_nan=False) + "\n")

    write("summary.json", report)
    write("predictions.json", report["luna"])
    write("speech-coverage.json", report["azure"])
    private_write(
        output / "samples.jsonl",
        "".join(json.dumps(row, allow_nan=False) + "\n" for row in report["azure"]["samples"]),
    )
    inputs, azure, luna = report["input"], report["azure"], report["luna"]
    scores = ", ".join(f"{key.upper()}={luna['scores'].get(key)}" for key in CRITERIA)
    lines = [
        "# Speaking audio replay",
        "",
        f"Mode: **{report['mode']}**; status: **{report['status']}**.",
        "",
        "## Input",
        "",
        f"Files: {inputs['file_count']}; source: {inputs['source_duration_ms'] / 1000:.3f}s; "
        f"selected candidate: {inputs['candidate_duration_ms'] / 1000:.3f}s.",
        f"Candidate-only verified: {inputs['candidate_only_verified']}; Parts: {inputs['part_counts']}.",
        "",
        "## Azure Speech",
        "",
        f"Complete/partial/failed/unknown streams: {azure['complete']}/{azure['partial']}/{azure['failed']}/{azure['unknown']}.",
        f"Recorded attempts: {azure['recorded_attempts']}; new attempts: {azure['new_attempts']}; "
        f"submitted audio: {azure['submitted_audio_ms'] / 1000:.3f}s.",
        f"Native/API latency: {azure['latency_ms']} ms; billing uncertain: {azure['billing_uncertain']}.",
        f"Word timing coverage: {azure['word_timing_coverage']}; "
        f"pronunciation word coverage: {azure['pronunciation_word_coverage']}; "
        f"prosody observed: {azure['prosody_observed']}; VAD available: {azure['vad_available']}.",
        "",
        "## Luna",
        "",
        f"{scores}; Overall={luna['overall']}.",
        f"Missing evidence/errors: {luna['reasons']}.",
        f"Observed calls: {luna['provider_calls']}; latency: {luna['latency_ms']} ms; usage: {luna['usage']}.",
        f"Provenance: {luna['provenance']}.",
        "",
        "## Evaluation",
        "",
        f"Status: {report['evaluation']['status']}.",
        "```json",
        json.dumps(report["evaluation"], indent=2, allow_nan=False),
        "```",
        "",
        "## Safety",
        "",
        "Technical recognition success does not validate IELTS grading accuracy.",
        "Operator cost estimates are estimates, not provider invoice caps. "
        "Speech/prosody and Luna are billed independently; actual invoice cost is unknown.",
        f"Limits/estimate acceptance: {report['limits']}.",
        "",
        *[f"- {reason}" for reason in report["limitations"]],
        "",
        "Private source mappings, transcripts and feedback are in SENSITIVE-* files only.",
        "",
    ]
    private_write(output / "summary.md", "\n".join(lines))
