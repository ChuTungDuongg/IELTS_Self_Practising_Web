"""Speaking scorer component only: fake transcript/acoustics/LLM, no DB/ASR/HTTP.

The two-slot gate belongs to this generator, NOT the production Speaking worker.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from benchmarks.load.source_identity import source_identity

from app.providers.speaking_llm.base import Completion
from app.services.speaking_scorer import SpeakingScorer, build_attempt_evidence

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def fictional_evidence():
    features = {
        "cache_key": "fake-features",
        "source_audio_fingerprint": "fake-audio",
        "quality": {
            "state": "AUDIO_OK",
            "assessable": True,
            "cache_key": "fake-quality",
            "source_audio_fingerprint": "fake-audio",
            "config": {},
            "metrics": {
                "duration_seconds": 10,
                "speech_seconds": 8,
                "rms": 0.1,
                "clipping_ratio": 0,
                "background_proxy_ratio": 0,
            },
        },
        "fluency": {
            "timing_status": "COMPLETE",
            "total_duration_seconds": 10,
            "word_count": 8,
            "aligned_word_count": 8,
            "timing_coverage": 1,
            "filled_pause_count": 1,
            "token_repetition_count": 0,
            "phrase_repetition_count": 0,
            "false_start_count": 0,
            "self_correction_count": 0,
        },
        "pronunciation": {
            "status": "AVAILABLE",
            "version": "alignment-prosody-v1",
            "source_audio_fingerprint": "fake-audio",
            "alignment_word_count": 8,
            "alignment_coverage": 1,
            "confidence_coverage": 1,
            "mean_alignment_confidence": 0.9,
            "rms": 0.1,
            "energy_cv": 0.2,
            "acoustic_frame_count": 30,
            "word_duration_cv": 0.3,
        },
    }
    return build_attempt_evidence(
        [
            {
                "response_id": uuid5(NAMESPACE_URL, f"fake-response-{part}"),
                "prompt_id": uuid5(NAMESPACE_URL, f"fake-prompt-{part}"),
                "part_number": part,
                "prompt_type": "LONG_TURN" if part == 2 else "SHORT_ANSWER",
                "prompt_text": "Describe a fictional garden.",
                "cue_points": ["Invent a detail"],
                "verbatim": "I um enjoy a fictional garden in Nerula.",
                "clean": "I enjoy a fictional garden in Nerula.",
                "words": [],
                "features": features,
            }
            for part in (1, 2, 3)
        ]
    )


class FakeProvider:
    def __init__(self, delay):
        self.delay, self.calls, self.active, self.peak = delay, 0, 0, 0

    async def ensure_ready(self):
        pass

    async def complete(self, messages, schema, *, options=None):
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
            value = (
                {"score": 6.5}
                if "score" in schema["properties"]
                else {
                    "feedback": "Fictional feedback.",
                    "strengths": ["Clear invented example"],
                    "improvements": ["Extend the fictional detail"],
                }
            )
            return Completion(text=json.dumps(value))
        finally:
            self.active -= 1


async def measure(*, jobs=5, concurrency=2, delay=0.02):
    if not 1 <= jobs <= 10 or not 1 <= concurrency <= 4 or not 0 <= delay <= 1:
        raise ValueError("Bounded local fake probe only")
    provider = FakeProvider(delay)
    gate = asyncio.Semaphore(concurrency)
    evidence = fictional_evidence()
    queued_at = perf_counter()
    waits, completions = [], []
    executing = peak = scores = completed_criteria = completed = 0

    async def run():
        nonlocal executing, peak, scores, completed_criteria, completed
        async with gate:
            waits.append((perf_counter() - queued_at) * 1000)
            executing += 1
            peak = max(peak, executing)
            try:
                scorer = SpeakingScorer(provider)

                async def checkpoint(result):
                    nonlocal scores
                    assert result.status == "SCORE_READY" and result.score == 6.5
                    scores += 1

                for criterion in ("fc", "lr", "gra", "pr"):
                    result = await scorer.score_criterion(criterion, evidence, checkpoint)
                    if result.status != "COMPLETED" or result.score != 6.5:
                        raise RuntimeError("Fake scoring contract failed")
                    completed_criteria += 1
                completed += 1
                completions.append((perf_counter() - queued_at) * 1000)
            finally:
                executing -= 1

    await asyncio.gather(*(run() for _ in range(jobs)))
    # Separate cancellation control: transport-free scorer sleep must unwind.
    blocked = FakeProvider(1)

    async def no_checkpoint(_):
        pass

    job = asyncio.create_task(
        SpeakingScorer(blocked).score_criterion("fc", evidence, no_checkpoint)
    )
    for _ in range(100):
        if blocked.active:
            break
        await asyncio.sleep(0)
    job.cancel()
    await asyncio.gather(job, return_exceptions=True)
    return {
        "scope": "SpeakingScorer component; fake transcript/acoustic evidence/LLM; no DB/audio/ASR/network",
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "source_identity": await asyncio.to_thread(source_identity, BACKEND),
        "jobs": jobs,
        "generator_concurrency": concurrency,
        "fake_call_delay_ms": delay * 1000,
        "completed": completed,
        "score_checkpoints": scores,
        "completion_checkpoints": completed_criteria,
        "provider_calls": provider.calls,
        "peak_executing_jobs": peak,
        "peak_fake_provider_calls": provider.peak,
        "calls_left_active": provider.active,
        "cancel_drained": blocked.active == 0 and job.cancelled(),
        "queue_wait_ms": {"samples": waits, "median": median(waits), "max": max(waits)},
        "accepted_to_completed_ms": {
            "samples": completions,
            "median": median(completions),
            "max": max(completions),
        },
        "limitations": [
            "Generator gate is not production admission control",
            "Checkpoints counted in memory; durable recovery verified only in PostgreSQL tests",
            "No real audio privacy/normalization/ASR throughput or grading quality measurement",
            "No inference capacity, token usage or cost claim",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(measure())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Fake Speaking component report saved; real inference capacity NOT VERIFIED")


if __name__ == "__main__":
    main()
