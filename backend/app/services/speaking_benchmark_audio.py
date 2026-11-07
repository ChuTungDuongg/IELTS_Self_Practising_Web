"""Inference-safe P1 approval input. Human labels are deliberately not imported."""

import asyncio
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from app.evaluation.speaking.replay_audio import normalize_window, probe_audio
from app.schemas.speaking_benchmark import ReviewDraft
from app.services.speaking_audio import await_audio_thread, fingerprint
from app.services.speaking_benchmark import failure
from app.services.speaking_benchmark_review import manifest_for_review


def approved_projection(sample, review, result, max_response_ms):
    if not review.approved_at or not review.manifest or not review.fingerprint:
        raise failure("SPEAKING_BENCHMARK_APPROVED_REVIEW_REQUIRED", 409)
    if sample.source_sha256 != result.source_sha256:
        raise failure("REPLAY_APPROVED_SOURCE_CHANGED", 409)
    manifest = manifest_for_review(
        result, ReviewDraft.model_validate(review.draft), max_response_ms
    )
    serialized = manifest.model_dump(mode="json")
    if serialized != review.manifest or review.fingerprint != fingerprint(
        [sample.source_sha256, result.identity, serialized]
    ):
        raise failure("REPLAY_APPROVED_SOURCE_CHANGED", 409)
    if manifest.grading_limitations():
        raise failure("SPEAKING_BENCHMARK_APPROVED_REVIEW_REQUIRED", 409)
    return manifest, [
        "HISTORICAL_APPROVED_REVIEW"
    ] if review.revision != sample.review_revision else []


async def load_approved_input(service, sample_id, revision):
    sample = await service.owned(sample_id)
    review, result = await service.review_row(sample, revision)
    manifest, warnings = approved_projection(
        sample, review, result, service.settings.speaking_max_decoded_seconds * 1000
    )
    return sample, review, manifest, warnings


@asynccontextmanager
async def materialize_approved_audio(storage, key, manifest, source_sha256, settings):
    from app.evaluation.speaking.diarization_backend import LocalDiarizer

    resolved = await await_audio_thread(asyncio.to_thread(LocalDiarizer().audio_settings, settings))
    # materialize is a private storage context, independent of local/S3/R2.
    context = storage.materialize(
        key, max_bytes=settings.speaking_benchmark_max_upload_mb * 1024**2
    )
    source = await await_audio_thread(asyncio.to_thread(context.__enter__))
    try:
        with tempfile.TemporaryDirectory(prefix="benchmark-grading-") as directory:
            root = Path(directory)
            source_name = manifest.source or manifest.segments[0].source
            if any((s.source or manifest.source) != source_name for s in manifest.segments):
                raise failure("REPLAY_APPROVED_SOURCE_CHANGED", 409)
            await await_audio_thread(asyncio.to_thread(shutil.copyfile, source, root / source_name))
            metadata = await await_audio_thread(
                asyncio.to_thread(probe_audio, root / source_name, resolved)
            )
            if metadata["sha256"] != source_sha256:
                raise failure("REPLAY_APPROVED_SOURCE_CHANGED", 409)
            yield root, metadata, resolved
    finally:
        await await_audio_thread(asyncio.to_thread(context.__exit__, None, None, None))


async def normalized_segment(root, metadata, manifest, segment, index, settings):
    return await await_audio_thread(
        asyncio.to_thread(
            normalize_window,
            root,
            segment.source or manifest.source,
            metadata,
            segment,
            root / f"candidate-{index}.wav",
            settings,
        )
    )
