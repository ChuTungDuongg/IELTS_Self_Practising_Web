"""Private evaluation anchors, never a production ingestion path."""

import hashlib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.evaluation.task1.manifest import BenchmarkInputError
from app.evaluation.task1.models import digest
from app.schemas.writing_anchors import AnchorRecord, AnchorSnapshot
from app.services.writing_anchors import WritingAnchorService


def normalized_essay_hash(essay: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", essay).casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AnchorSource:
    snapshot: AnchorSnapshot = field(default_factory=AnchorSnapshot)
    sample_ids: frozenset[str] = frozenset()

    @property
    def digest(self):
        return digest(
            {
                "snapshot": self.snapshot.model_dump(mode="json"),
                "sample_ids": sorted(self.sample_ids),
            }
        )

    @property
    def density(self):
        return {
            t: {
                str(b): sum(
                    getattr(a.human_scores, t) == b
                    for a in self.snapshot.anchors
                    if a.task_number == 1
                )
                for b in range(10)
            }
            for t in ("cc", "lr", "gra")
        }


class PrivateAnchor(AnchorRecord):
    sample_id: str = Field(min_length=1, max_length=80)
    provenance: str = Field(min_length=1, max_length=2000, repr=False)

    @field_validator("sample_id", "provenance", "prompt", "response_text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Blank private anchor field")
        return value


class PrivateBank(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    id: UUID
    version: int = Field(ge=1)
    anchors: list[PrivateAnchor] = Field(max_length=10000)


def load_anchor_manifest(path: Path) -> AnchorSource:
    try:
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError()
        bank = PrivateBank.model_validate_json(path.read_text(encoding="utf-8"))
        if len({a.id for a in bank.anchors}) != len(bank.anchors) or len(
            {a.sample_id for a in bank.anchors}
        ) != len(bank.anchors):
            raise ValueError()
        return AnchorSource(
            AnchorSnapshot(
                id=bank.id,
                version=bank.version,
                anchors=tuple(
                    AnchorRecord.model_validate(a.model_dump(exclude={"sample_id", "provenance"}))
                    for a in bank.anchors
                ),
            ),
            frozenset(a.sample_id for a in bank.anchors),
        )
    except (OSError, UnicodeError, ValueError):
        raise BenchmarkInputError("BENCHMARK_ANCHOR_MANIFEST_INVALID") from None


async def load_postgres_anchors(settings) -> AnchorSource:
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            snapshot = await WritingAnchorService(session).active_snapshot()
            return AnchorSource(snapshot, frozenset(str(a.id) for a in snapshot.anchors))
    finally:
        await engine.dispose()


def guard_leakage(items, source: AnchorSource):
    hashes = {normalized_essay_hash(a.response_text) for a in source.snapshot.anchors}
    if any(
        item.sample.id in source.sample_ids or normalized_essay_hash(item.sample.essay) in hashes
        for item in items
    ):
        raise BenchmarkInputError("BENCHMARK_ANCHOR_LEAKAGE")
