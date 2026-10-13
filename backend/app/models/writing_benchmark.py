"""One admin-authored ground-truth bank, independent of learner records."""

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domains.writing.task_types import TASK_ONE_TYPES
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WritingBenchmarkSplit, WritingBenchmarkStatus

SCORE_FIELDS = ("human_ta_tr", "human_cc", "human_lr", "human_gra")
TASK_TYPES_SQL = ",".join(f"'{value}'" for value in sorted(TASK_ONE_TYPES))


class WritingBenchmarkSample(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "writing_benchmark_samples"
    __table_args__ = (
        UniqueConstraint("task_number", "sequence_number"),
        CheckConstraint("task_number IN (1,2)", name="task_number"),
        CheckConstraint("sequence_number BETWEEN 1 AND 100", name="sequence_number"),
        CheckConstraint("revision >= 0", name="revision"),
        CheckConstraint(
            f"task1_task_type IS NULL OR task1_task_type IN ({TASK_TYPES_SQL})", name="task1_type"
        ),
        CheckConstraint(
            "task_number = 1 OR (task1_task_type IS NULL AND task1_image_key IS NULL)",
            name="task2_text_only",
        ),
        CheckConstraint(
            "length(prompt) <= 20000 AND length(essay) <= 100000", name="content_length"
        ),
        CheckConstraint("source_note IS NULL OR length(source_note) <= 2000", name="source_length"),
        *(
            CheckConstraint(
                f"{field} IS NULL OR ({field} BETWEEN 0 AND 9 AND {field} * 2 = floor({field} * 2))",
                name=f"{field}_half_band",
            )
            for field in SCORE_FIELDS
        ),
        CheckConstraint(
            "status != 'COMPLETE' OR (prompt ~ '[^[:space:]]' AND essay ~ '[^[:space:]]' AND "
            + " AND ".join(f"{field} IS NOT NULL" for field in SCORE_FIELDS)
            + " AND (task_number = 2 OR (task1_task_type IS NOT NULL AND task1_image_key IS NOT NULL AND length(task1_image_key) > 0)))",
            name="complete",
        ),
    )

    task_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[WritingBenchmarkStatus] = mapped_column(
        Enum(WritingBenchmarkStatus, name="writing_benchmark_status"),
        default=WritingBenchmarkStatus.DRAFT,
        server_default="DRAFT",
        nullable=False,
    )
    split: Mapped[WritingBenchmarkSplit] = mapped_column(
        Enum(WritingBenchmarkSplit, name="writing_benchmark_split"),
        default=WritingBenchmarkSplit.DEV,
        server_default="DEV",
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    essay: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    task1_task_type: Mapped[str | None] = mapped_column(String(40))
    task1_image_key: Mapped[str | None] = mapped_column(String(512))
    human_ta_tr: Mapped[Decimal | None] = mapped_column(Numeric())
    human_cc: Mapped[Decimal | None] = mapped_column(Numeric())
    human_lr: Mapped[Decimal | None] = mapped_column(Numeric())
    human_gra: Mapped[Decimal | None] = mapped_column(Numeric())
    source_note: Mapped[str | None] = mapped_column(Text)
    redistributable: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    @property
    def code(self) -> str:
        return f"T{self.task_number}-{self.sequence_number:03d}"
