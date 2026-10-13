"""Stable canonical manifests and private images, exported from one locked snapshot."""

import asyncio
import csv
import io
import json
import zipfile
from types import SimpleNamespace

from pydantic import TypeAdapter, ValidationError

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.evaluation.task1.manifest import BenchmarkInputError, load_image
from app.evaluation.task1.models import BenchmarkSample as Task1Sample
from app.evaluation.task2.models import BenchmarkSample as Task2Sample
from app.evaluation.writing.metrics import overall_score
from app.repositories.writing_benchmark import WritingBenchmarkRepository
from app.services.writing_benchmark import owned_image_path, scores
from app.storage import LocalAssetStorage

README = """Writing benchmark source bundle
JSONL is canonical; CSV is an inspection convenience. Only COMPLETE samples are included.
schema_version is file-format compatibility, not a dataset version.
Source material may be private/licensed. redistributable=false by default.
Clone the repository and install backend dependencies with uv sync --locked --group dev.
From the repository root:
uv run --project backend python scripts/benchmark_task1.py --manifest <bundle>/task1.jsonl --split dev --dry-run
uv run --project backend python scripts/benchmark_task2.py --manifest <bundle>/task2.jsonl --split dev --dry-run
Configure provider secrets in your local/Colab environment; remove --dry-run to evaluate.
Evaluation sends prompt/essay (and Task 1 image) to the configured provider.
No production database credentials, admin token, or production API connection are needed.
Reports remain local. Human labels never enter inference requests.
"""


def _common(row):
    return dict(
        schema_version=1,
        id=f"T{row.task_number}-{row.sequence_number:03d}",
        split=row.split.lower(),
        prompt=row.prompt,
        essay=row.essay,
        human_scores=scores(row),
        raters=1,
        provenance=row.source_note
        if row.source_note and row.source_note.strip()
        else "admin-labelled benchmark sample",
        redistributable=row.redistributable,
    )


def task1_manifest_sample(row, image_path):
    return Task1Sample(
        **_common(row), task_type=row.task1_task_type, image_path=image_path, visual_truth=None
    )


def task2_manifest_sample(row):
    return Task2Sample(**_common(row))


def manifest_schema():
    return TypeAdapter(Task1Sample | Task2Sample).json_schema()


def write_csv(rows, task_number):
    first = "ta" if task_number == 1 else "tr"
    fields = [
        "id",
        "split",
        *(["task_type", "image_path"] if task_number == 1 else []),
        "prompt",
        "essay",
        "human_" + first,
        "human_cc",
        "human_lr",
        "human_gra",
        "human_overall",
        "provenance",
        "redistributable",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for sample in rows:
        values = sample.model_dump()
        human = sample.human_scores.scores()
        values.update({"human_" + trait: value for trait, value in human.items()})
        values["human_overall"] = overall_score(human, traits=tuple(human))
        writer.writerow({key: values[key] for key in fields})
    return output.getvalue()


def jsonl(rows):
    lines = []
    for row in rows:
        values = row.model_dump(mode="json")
        values["human_scores"] = {
            trait: float(score) for trait, score in row.human_scores.scores().items()
        }
        lines.append(json.dumps(values, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + ("\n" if lines else "")


class WritingBenchmarkExportService:
    def __init__(self, session, storage=None):
        self.session = session
        self.repo = WritingBenchmarkRepository(session)
        self.storage = storage or LocalAssetStorage(get_settings().resolved_storage_root)

    async def export(self, path):
        try:
            async with self.session.begin():
                rows = await self.repo.complete_rows(lock_shared=True)
                # Snapshot scalar values only: the staging thread never uses a Session.
                snapshots = [
                    SimpleNamespace(
                        **{column.key: getattr(row, column.key) for column in row.__table__.columns}
                    )
                    for row in rows
                ]
                worker = asyncio.create_task(asyncio.to_thread(self._write_bundle, path, snapshots))
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    # Keep row locks until the worker finishes reading live assets.
                    await worker
                    raise
        except (AppError, BenchmarkInputError, ValidationError, OSError):
            path.unlink(missing_ok=True)
            raise AppError(
                "BENCHMARK_EXPORT_INVALID",
                "The benchmark bundle could not be exported. Check completed samples and images.",
                422,
            ) from None
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def _write_bundle(self, path, rows):
        manifests = {1: [], 2: []}
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("images/", b"")
            for row in rows:
                if row.task_number == 1:
                    source = owned_image_path(self.storage, row.id, row.task1_image_key)
                    image = load_image(source)
                    image_path = f"images/T1-{row.sequence_number:03d}{source.suffix}"
                    manifests[1].append(task1_manifest_sample(row, image_path))
                    archive.writestr(image_path, image.data)
                else:
                    manifests[2].append(task2_manifest_sample(row))
            for task in (1, 2):
                archive.writestr(f"task{task}.jsonl", jsonl(manifests[task]))
                archive.writestr(f"task{task}.csv", write_csv(manifests[task], task))
            archive.writestr(
                "manifest.schema.json",
                json.dumps(manifest_schema(), ensure_ascii=False, indent=2) + "\n",
            )
            archive.writestr("README.txt", README)
