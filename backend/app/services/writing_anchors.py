from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domains.scoring.anchor_ladders import contiguous_ladder
from app.models import Test, WritingAnchorSet, WritingHumanAnchor, WritingTask
from app.repositories.writing_anchors import (
    WritingAnchorRepository,
    anchor_query,
    frozen_condition,
    task_query,
)
from app.schemas.writing_anchors import (
    LANGUAGE_TRAITS,
    AnchorCoverageResponse,
    AnchorDetail,
    AnchorPage,
    AnchorRecord,
    AnchorSetResponse,
    AnchorSnapshot,
    AnchorSummary,
    CriterionCoverage,
    FrozenTaskPage,
    FrozenWritingTask,
    HumanAnchorInput,
    HumanAnchorScores,
    ResearchTaskCoverage,
)


def task_dto(task, version, test):
    return FrozenWritingTask(
        id=task.id,
        test_version_id=version.id,
        test_title=test.title,
        version_number=version.version_number,
        task_number=task.task_number,
        task_type=task.task_type,
        prompt_preview=task.prompt[:240],
    )


def scores(anchor):
    return HumanAnchorScores(
        **{trait: getattr(anchor, f"{trait}_score") for trait in ("ta", *LANGUAGE_TRAITS)}
    )


def detail(row):
    anchor, task, version, test = row
    return AnchorDetail(
        id=anchor.id,
        anchor_set_id=anchor.anchor_set_id,
        task=task_dto(task, version, test),
        word_count=len(anchor.response_text.split()),
        human_scores=scores(anchor),
        created_at=anchor.created_at,
        response_text=anchor.response_text,
        admin_note=anchor.admin_note,
        provenance=anchor.provenance,
    )


def criterion_coverage(anchors, trait):
    counts = Counter(getattr(anchor.human_scores, trait) for anchor in anchors)
    all_counts = {str(Decimal(index) / 2): counts[Decimal(index) / 2] for index in range(19)}
    # Stable labels for both whole and half bands in the UI/API.
    all_counts = {format(Decimal(key).normalize(), "f"): value for key, value in all_counts.items()}
    ladder = list(contiguous_ladder(counts))
    mature = all(counts[Decimal(band)] >= 3 for band in range(5, 10))
    readiness = (
        "RECOMMENDED_COVERAGE"
        if mature
        else "PAIRWISE_USABLE"
        if ladder
        else "PARTIAL"
        if anchors
        else "EMPTY"
    )
    return CriterionCoverage(
        criterion=trait,
        counts=all_counts,
        ladder=ladder,
        readiness=readiness,
        pilot_complete=all(counts[Decimal(band)] >= 2 for band in (6, 7, 8)),
    )


class WritingAnchorService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = WritingAnchorRepository(session)

    @asynccontextmanager
    async def transaction(self):
        if self.session.in_transaction():
            yield
        else:
            async with self.session.begin():
                yield

    async def _set(self, set_id, *, draft=False):
        row = await self.repository.set(set_id, lock=draft)
        if row is None:
            raise AppError("ANCHOR_SET_NOT_FOUND", "The anchor set does not exist.", 404)
        if draft and row.status != "DRAFT":
            raise AppError(
                "ANCHOR_SET_IMMUTABLE", "Create the next draft to change these anchors.", 409
            )
        return row

    async def list_sets(self):
        async with self.transaction():
            return [AnchorSetResponse.model_validate(row) for row in await self.repository.sets()]

    async def create_draft(self, admin_id: UUID, name: str):
        async with self.transaction():
            await self.repository.lifecycle_lock()
            if await self.session.scalar(
                select(WritingAnchorSet.id).where(WritingAnchorSet.status == "DRAFT")
            ):
                raise AppError("ANCHOR_DRAFT_EXISTS", "An editable draft already exists.", 409)
            active = await self.repository.active()
            row = WritingAnchorSet(
                name=name,
                version=await self.repository.next_version(),
                status="DRAFT",
                created_by_id=admin_id,
            )
            self.session.add(row)
            await self.session.flush()
            if active:
                for anchor, *_ in await self.repository.rows(active.id):
                    self.session.add(
                        WritingHumanAnchor(
                            anchor_set_id=row.id,
                            writing_task_id=anchor.writing_task_id,
                            response_text=anchor.response_text,
                            created_by_id=anchor.created_by_id,
                            admin_note=anchor.admin_note,
                            provenance=anchor.provenance,
                            **{
                                f"{trait}_score": getattr(anchor, f"{trait}_score")
                                for trait in ("ta", *LANGUAGE_TRAITS)
                            },
                        )
                    )
            await self.session.flush()
            return AnchorSetResponse.model_validate(row)

    async def activate(self, admin_id: UUID, set_id: UUID):
        async with self.transaction():
            await self.repository.lifecycle_lock()
            row = await self._set(set_id, draft=True)
            active = await self.repository.active()
            now = datetime.now(UTC)
            if active:
                active.status, active.retired_at = "RETIRED", now
                await self.session.flush()  # free the single ACTIVE slot first
            row.status, row.activated_at = "ACTIVE", now
            await self.session.flush()
            return AnchorSetResponse.model_validate(row)

    async def _frozen_task(self, task_id):
        row = (
            await self.session.execute(
                task_query().where(WritingTask.id == task_id, frozen_condition())
            )
        ).first()
        if row is None:
            raise AppError(
                "ANCHOR_FROZEN_TASK_REQUIRED", "Select an existing frozen Writing task.", 422
            )
        return row

    def _apply(self, anchor, body):
        anchor.writing_task_id, anchor.response_text = body.writing_task_id, body.response_text
        anchor.admin_note, anchor.provenance = body.admin_note, body.provenance
        for trait in ("ta", *LANGUAGE_TRAITS):
            setattr(anchor, f"{trait}_score", getattr(body.human_scores, trait))

    async def create_anchor(self, admin_id: UUID, set_id: UUID, body: HumanAnchorInput):
        async with self.transaction():
            await self._set(set_id, draft=True)
            task, version, test = await self._frozen_task(body.writing_task_id)
            row = WritingHumanAnchor(anchor_set_id=set_id, created_by_id=admin_id)
            self._apply(row, body)
            self.session.add(row)
            await self.session.flush()
            return detail((row, task, version, test))

    async def _anchor(self, anchor_id):
        row = await self.repository.anchor(anchor_id)
        if row is None:
            raise AppError("HUMAN_ANCHOR_NOT_FOUND", "The human anchor does not exist.", 404)
        return row

    async def get_anchor(self, anchor_id):
        async with self.transaction():
            return detail(await self._anchor(anchor_id))

    async def update_anchor(self, admin_id: UUID, anchor_id: UUID, body: HumanAnchorInput):
        async with self.transaction():
            row, *_ = await self._anchor(anchor_id)
            await self._set(row.anchor_set_id, draft=True)
            task, version, test = await self._frozen_task(body.writing_task_id)
            self._apply(row, body)
            await self.session.flush()
            return detail((row, task, version, test))

    async def delete_anchor(self, anchor_id: UUID):
        async with self.transaction():
            row, *_ = await self._anchor(anchor_id)
            await self._set(row.anchor_set_id, draft=True)
            await self.session.delete(row)
            await self.session.flush()

    async def list_tasks(self, *, search=None, task_number=None, offset=0, limit=25):
        async with self.transaction():
            query = task_query().where(frozen_condition())
            if task_number is not None:
                query = query.where(WritingTask.task_number == task_number)
            if search:
                from sqlalchemy import or_

                query = query.where(
                    or_(
                        Test.title.icontains(search, autoescape=True),
                        WritingTask.prompt.icontains(search, autoescape=True),
                    )
                )
            total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
            rows = (
                await self.session.execute(
                    query.order_by(Test.title, WritingTask.id).offset(offset).limit(limit)
                )
            ).all()
            return FrozenTaskPage(
                items=[task_dto(*row) for row in rows], total=total, offset=offset, limit=limit
            )

    async def list_anchors(
        self,
        *,
        set_id=None,
        search=None,
        task_number=None,
        writing_task_id=None,
        task_type=None,
        status=None,
        offset=0,
        limit=25,
    ):
        async with self.transaction():
            query = anchor_query().join(
                WritingAnchorSet, WritingHumanAnchor.anchor_set_id == WritingAnchorSet.id
            )
            if set_id:
                query = query.where(WritingHumanAnchor.anchor_set_id == set_id)
            if task_number is not None:
                query = query.where(WritingTask.task_number == task_number)
            if writing_task_id:
                query = query.where(WritingTask.id == writing_task_id)
            if task_type:
                query = query.where(WritingTask.task_type == task_type)
            if status:
                query = query.where(WritingAnchorSet.status == status)
            if search:
                from sqlalchemy import or_

                query = query.where(
                    or_(
                        Test.title.icontains(search, autoescape=True),
                        WritingTask.prompt.icontains(search, autoescape=True),
                    )
                )
            total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
            rows = (
                await self.session.execute(
                    query.order_by(WritingHumanAnchor.created_at.desc(), WritingHumanAnchor.id)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return AnchorPage(
                items=[
                    AnchorSummary.model_validate(
                        detail(row).model_dump(include=set(AnchorSummary.model_fields))
                    )
                    for row in rows
                ],
                total=total,
                offset=offset,
                limit=limit,
            )

    async def _snapshot(self, row):
        if row is None:
            return AnchorSnapshot()
        return AnchorSnapshot(
            id=row.id,
            version=row.version,
            anchors=tuple(
                AnchorRecord(
                    id=anchor.id,
                    writing_task_id=task.id,
                    test_version_id=version.id,
                    task_number=task.task_number,
                    task_type=task.task_type,
                    prompt=task.prompt,
                    response_text=anchor.response_text,
                    human_scores=scores(anchor),
                )
                for anchor, task, version, _ in await self.repository.rows(row.id)
            ),
        )

    async def active_snapshot(self):
        async with self.transaction():
            return await self._snapshot(await self.repository.active())

    async def snapshot(self, set_id: UUID):
        async with self.transaction():
            row = await self._set(set_id)
            if row.status == "DRAFT":
                raise AppError(
                    "ANCHOR_SNAPSHOT_NOT_FROZEN", "A draft is not a scoring snapshot.", 409
                )
            return await self._snapshot(row)

    async def coverage(self, *, node_budget=2):
        async with self.transaction():
            active = await self.repository.active()
            snapshot = await self._snapshot(active)
            one = [anchor for anchor in snapshot.anchors if anchor.task_number == 1]
            two = [anchor for anchor in snapshot.anchors if anchor.task_number == 2]
            research = []
            if active:
                task_rows = {
                    task.id: task_dto(task, version, test)
                    for _, task, version, test in await self.repository.rows(active.id)
                }
                for task_id in sorted({anchor.writing_task_id for anchor in one}, key=str):
                    row = criterion_coverage(
                        [anchor for anchor in one if anchor.writing_task_id == task_id], "ta"
                    )
                    research.append(
                        ResearchTaskCoverage(**row.model_dump(), task=task_rows[task_id])
                    )
            return AnchorCoverageResponse(
                active_set=AnchorSetResponse.model_validate(active) if active else None,
                production_task1=[criterion_coverage(one, trait) for trait in LANGUAGE_TRAITS],
                research_task1_ta=research,
                research_task2=[
                    criterion_coverage(two, trait) for trait in ("ta", *LANGUAGE_TRAITS)
                ],
                recommendations=[
                    "Technical minimum: one human anchor at two adjacent whole bands.",
                    "Pilot: approximately two anchors per band at 6, 7 and 8 for CC/LR/GRA.",
                    "Mature: approximately three per band at 5–9, with extra density at 6–8.",
                    "Initial practical target: 20–30 carefully human-labelled Task 1 responses; similar Task 2 data later.",
                    "Recommendations are operational guidance, not IELTS rules or statistical guarantees.",
                    "TA labels are evaluation data; Task 2 anchors are for evaluation/future TACS.",
                ],
                node_budget=node_budget,
            )
