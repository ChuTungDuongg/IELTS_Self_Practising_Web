"""Classwork lifecycle and ordering; every write locks its classroom."""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import ClassroomAssignment
from app.models.classroom_classwork import ClassroomContentItem, ClassroomResource, ClassroomSection
from app.models.classroom_posts import ClassroomPostResource
from app.repositories.classroom_classwork import ClassworkRepository
from app.schemas.classroom_classwork import (
    AssignmentPlacement,
    ClassworkResponse,
    ItemReorderRequest,
    ItemResponse,
    ReorderRequest,
    ResourceCreate,
    ResourceResponse,
    ResourceUpdate,
    SectionCreate,
    SectionResponse,
    SectionUpdate,
)
from app.services.classroom_capabilities import Capability
from app.services.classroom_content_access import ContentAccess
from app.storage.classroom import ClassroomResourceStorage
from app.storage.factory import get_asset_storage
from app.storage.local import StoredAsset

logger = logging.getLogger(__name__)


class ClassworkService:
    def __init__(self, session, actor):
        self.session = session
        self.access = ContentAccess(session, actor)
        self.repository = ClassworkRepository(session)

    async def _snapshot(self, room):
        sections, resources, items = await self.repository.snapshot(
            room.id, staff=self.access.staff(room)
        )
        return ClassworkResponse(
            revision=room.content_revision,
            sections=[SectionResponse.model_validate(row) for row in sections],
            resources=[ResourceResponse.model_validate(row) for row in resources],
            items=[ItemResponse.model_validate(row) for row in items],
            removed_assignment_ids=list(
                await self.session.scalars(
                    select(ClassroomAssignment.id).where(
                        ClassroomAssignment.classroom_id == room.id,
                        ClassroomAssignment.classwork_hidden.is_(True),
                    )
                )
            ),
        )

    async def get(self, classroom_id: UUID):
        async with self.session.begin():
            room = await self.access.room(classroom_id)
            return await self._snapshot(room)

    @staticmethod
    def _revision(room, expected):
        if room.content_revision != expected:
            raise AppError("CLASSWORK_CHANGED", "Classwork changed. Reload before reordering.", 409)

    async def _section(self, room, section_id):
        if section_id is None:
            return None
        section = await self.session.scalar(
            select(ClassroomSection).where(
                ClassroomSection.id == section_id, ClassroomSection.classroom_id == room.id
            )
        )
        if section is None:
            raise AppError("SECTION_NOT_FOUND", "The section does not exist.", 404)
        return section

    async def create_section(self, classroom_id, data: SectionCreate):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            sections = await self.repository.sections(room.id)
            row = ClassroomSection(
                classroom_id=room.id, position=len(sections), **data.model_dump()
            )
            self.session.add(row)
            room.content_revision += 1
            await self.session.flush()
            return SectionResponse.model_validate(row)

    async def update_section(self, classroom_id, section_id, data: SectionUpdate):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            row = await self._section(room, section_id)
            for key, value in data.model_dump(exclude_unset=True).items():
                setattr(row, key, value)
            room.content_revision += 1
            await self.session.flush()
            await self.session.refresh(row)
            return SectionResponse.model_validate(row)

    async def reorder_sections(self, classroom_id, data: ReorderRequest):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            self._revision(room, data.expected_revision)
            rows = await self.repository.sections(room.id)
            if set(data.ids) != {row.id for row in rows}:
                raise AppError(
                    "CLASSWORK_ORDER_INVALID", "Include every section exactly once.", 422
                )
            positions = {id: index for index, id in enumerate(data.ids)}
            for row in rows:
                row.position = positions[row.id]
            room.content_revision += 1
            await self.session.flush()
            return await self._snapshot(room)

    async def _attach_resource(self, room, resource, section_id):
        await self._section(room, section_id)
        items = await self.repository.items(room.id)
        resource.created_by_user_id = self.access.actor.id
        if resource.status == "PUBLISHED":
            resource.published_at = datetime.now(UTC)
        self.session.add(resource)
        await self.session.flush()
        self.session.add(
            ClassroomContentItem(
                classroom_id=room.id,
                section_id=section_id,
                resource_id=resource.id,
                position=sum(item.section_id == section_id for item in items),
            )
        )
        room.content_revision += 1
        await self.session.flush()
        return ResourceResponse.model_validate(resource)

    async def create_resource(self, classroom_id, data: ResourceCreate):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            row = ClassroomResource(classroom_id=room.id, **data.model_dump(exclude={"section_id"}))
            return await self._attach_resource(room, row, data.section_id)

    async def get_resource(self, classroom_id, resource_id):
        async with self.session.begin():
            room = await self.access.room(classroom_id)
            row = await self._resource(room, resource_id)
            return ResourceResponse.model_validate(row)

    async def _resource(self, room, resource_id):
        row = await self.repository.resource(room.id, resource_id, staff=self.access.staff(room))
        if row is None:
            raise AppError("RESOURCE_NOT_FOUND", "The resource does not exist.", 404)
        return row

    async def update_resource(self, classroom_id, resource_id, data: ResourceUpdate):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            row = await self._resource(room, resource_id)
            values = data.model_dump(exclude_unset=True)
            if row.kind == "FILE":
                if set(values) & {"body", "url"}:
                    raise AppError(
                        "RESOURCE_TARGET_INVALID", "Files have immutable storage references.", 422
                    )
            else:
                # Reuse complete input validation after merging partial updates.
                try:
                    ResourceCreate.model_validate(
                        {
                            key: values.get(key, getattr(row, key))
                            for key in ("title", "description", "kind", "status", "body", "url")
                        }
                    )
                except ValidationError as error:
                    raise AppError(
                        "RESOURCE_TARGET_INVALID", "Resource content does not match its type.", 422
                    ) from error
            for key, value in values.items():
                setattr(row, key, value)
            if row.status == "PUBLISHED" and row.published_at is None:
                row.published_at = datetime.now(UTC)
            room.content_revision += 1
            await self.session.flush()
            await self.session.refresh(row)
            return ResourceResponse.model_validate(row)

    async def place_assignment(self, classroom_id, data: AssignmentPlacement):
        async with self.session.begin():
            room = await self.access.room(
                classroom_id, mutation=True, owner=True, capability=Capability.ASSIGNMENTS
            )
            await self._section(room, data.section_id)
            assignment = await self.session.scalar(
                select(ClassroomAssignment).where(
                    ClassroomAssignment.id == data.assignment_id,
                    ClassroomAssignment.classroom_id == room.id,
                )
            )
            if assignment is None:
                raise AppError("ASSIGNMENT_NOT_FOUND", "The assignment does not exist.", 404)
            assignment.classwork_hidden = False
            items = await self.repository.items(room.id)
            row = next((item for item in items if item.assignment_id == assignment.id), None)
            if row is None:
                row = ClassroomContentItem(
                    classroom_id=room.id, assignment_id=assignment.id, position=0
                )
                self.session.add(row)
            old_section_id = row.section_id
            row.section_id = data.section_id
            target = [
                item for item in items if item.section_id == data.section_id and item is not row
            ] + [row]
            for position, item in enumerate(target):
                item.position = position
            if old_section_id != data.section_id:
                for position, item in enumerate(
                    item for item in items if item.section_id == old_section_id
                ):
                    item.position = position
            room.content_revision += 1
            await self.session.flush()
            return await self._snapshot(room)

    async def reorder_items(self, classroom_id, data: ItemReorderRequest):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            self._revision(room, data.expected_revision)
            await self._section(room, data.section_id)
            rows = await self.repository.items(room.id)
            # Moving an assignment across topics requires assignment management.
            # Resource moves still include the unchanged target assignments in ids.
            if any(
                row.assignment_id and row.id in data.ids and row.section_id != data.section_id
                for row in rows
            ):
                from app.services.classroom_capabilities import require_capability

                await require_capability(
                    self.session, self.access.actor, room, Capability.ASSIGNMENTS
                )
            by_id = {row.id: row for row in rows}
            target_ids = {row.id for row in rows if row.section_id == data.section_id}
            if not set(data.ids) <= by_id.keys() or not target_ids <= set(data.ids):
                raise AppError(
                    "CLASSWORK_ORDER_INVALID",
                    "Include all target content and only content from this classroom.",
                    422,
                )
            for position, id in enumerate(data.ids):
                by_id[id].section_id = data.section_id
                by_id[id].position = position
            source_sections = {row.section_id for row in rows} - {data.section_id}
            for source in source_sections:
                for position, row in enumerate(row for row in rows if row.section_id == source):
                    row.position = position
            room.content_revision += 1
            await self.session.flush()
            return await self._snapshot(room)

    async def delete_section(self, classroom_id, section_id, expected_revision=None):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            if expected_revision is not None:
                self._revision(room, expected_revision)
            section = await self._section(room, section_id)
            items = await self.repository.items(room.id)
            if section.status != "PUBLISHED":
                hidden_ids = [
                    item.resource_id
                    for item in items
                    if item.section_id == section.id and item.resource_id
                ]
                hidden_resources = await self.session.scalars(
                    select(ClassroomResource).where(
                        ClassroomResource.id.in_(hidden_ids),
                        ClassroomResource.status == "PUBLISHED",
                    )
                )
                for resource in hidden_resources:
                    # Removing a hidden parent must not publish its children.
                    resource.status = "DRAFT" if section.status == "DRAFT" else "ARCHIVED"
            moved = [item for item in items if item.section_id is None] + [
                item for item in items if item.section_id == section.id
            ]
            for position, item in enumerate(moved):
                item.section_id, item.position = None, position
            await self.session.flush()
            await self.session.delete(section)
            room.content_revision += 1
            await self.session.flush()
            return await self._snapshot(room)

    async def delete_resource(self, classroom_id, resource_id, expected_revision=None):
        key = None
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            if expected_revision is not None:
                self._revision(room, expected_revision)
            resource = await self._resource(room, resource_id)
            from app.services.classroom_deletion import remove_plan_references

            await remove_plan_references(
                self.session, room.id, self.access.actor.id, resource_id=resource.id
            )
            await self.session.execute(
                delete(ClassroomPostResource).where(
                    ClassroomPostResource.resource_id == resource.id
                )
            )
            key = resource.storage_key
            await self.session.execute(
                delete(ClassroomContentItem).where(
                    ClassroomContentItem.classroom_id == room.id,
                    ClassroomContentItem.resource_id == resource.id,
                )
            )
            await self.session.delete(resource)
            room.content_revision += 1
            await self.session.flush()
            response = await self._snapshot(room)
        if key:
            try:
                await self._compensate(
                    ClassroomResourceStorage(get_asset_storage(get_settings())), key
                )
            except OSError:
                logger.exception(
                    "Removed resource file cleanup failed; no active reference remains"
                )
        return response

    async def remove_assignment(self, classroom_id, item_id, expected_revision=None):
        async with self.session.begin():
            room = await self.access.room(
                classroom_id, mutation=True, owner=True, capability=Capability.ASSIGNMENTS
            )
            if expected_revision is not None:
                self._revision(room, expected_revision)
            item = await self.session.scalar(
                select(ClassroomContentItem).where(
                    ClassroomContentItem.classroom_id == room.id,
                    ClassroomContentItem.id == item_id,
                    ClassroomContentItem.assignment_id.is_not(None),
                )
            )
            if item is None:
                raise AppError(
                    "CLASSWORK_ITEM_NOT_FOUND", "The assignment reference does not exist.", 404
                )
            assignment = await self.session.get(ClassroomAssignment, item.assignment_id)
            assignment.classwork_hidden = True
            await self.session.delete(item)
            room.content_revision += 1
            await self.session.flush()
            return await self._snapshot(room)

    async def remove_assignment_reference(
        self, classroom_id, assignment_id, expected_revision=None
    ):
        """The same safe removal for canonical assignments without a placement row."""
        async with self.session.begin():
            room = await self.access.room(
                classroom_id, mutation=True, owner=True, capability=Capability.ASSIGNMENTS
            )
            if expected_revision is not None:
                self._revision(room, expected_revision)
            assignment = await self.session.scalar(
                select(ClassroomAssignment).where(
                    ClassroomAssignment.classroom_id == room.id,
                    ClassroomAssignment.id == assignment_id,
                )
            )
            if assignment is None:
                raise AppError("ASSIGNMENT_NOT_FOUND", "The assignment does not exist.", 404)
            assignment.classwork_hidden = True
            await self.session.execute(
                delete(ClassroomContentItem).where(
                    ClassroomContentItem.classroom_id == room.id,
                    ClassroomContentItem.assignment_id == assignment.id,
                )
            )
            room.content_revision += 1
            await self.session.flush()
            return await self._snapshot(room)

    async def upload(self, classroom_id, upload, data: SectionCreate, section_id=None):
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            await self._section(room, section_id)
        storage = ClassroomResourceStorage(get_asset_storage(get_settings()))
        filename = upload.filename or ""
        media_type = upload.content_type or "application/octet-stream"
        staging = asyncio.create_task(
            asyncio.to_thread(storage.store_resource, upload.file, filename, media_type)
        )
        stored = None
        try:
            stored = await asyncio.shield(staging)
            async with self.session.begin():
                room = await self.access.room(classroom_id, mutation=True, owner=True)
                row = ClassroomResource(
                    classroom_id=room.id,
                    kind="FILE",
                    storage_key=stored.relative_path,
                    original_filename=filename,
                    media_type=media_type,
                    size_bytes=stored.size,
                    **data.model_dump(),
                )
                response = await self._attach_resource(room, row, section_id)
            return response
        except BaseException:
            if stored is None:
                result = (await asyncio.gather(staging, return_exceptions=True))[0]
                if isinstance(result, StoredAsset):
                    stored = result
            if stored is not None:
                await self._compensate(storage, stored.relative_path)
            raise

    async def _compensate(self, storage, key):
        # Recheck durable references after a possibly lost commit acknowledgement.
        try:
            referenced = await self.session.scalar(
                select(ClassroomResource.id).where(ClassroomResource.storage_key == key)
            )
            await self.session.rollback()
        except BaseException:
            logger.exception("Resource storage compensation could not verify reference")
            return
        if referenced is None:
            await asyncio.to_thread(storage.delete, key)

    async def file(self, classroom_id, resource_id):
        async with self.session.begin():
            room = await self.access.room(classroom_id)
            row = await self._resource(room, resource_id)
            if row.kind != "FILE" or not row.storage_key:
                raise AppError("RESOURCE_NOT_FOUND", "The file does not exist.", 404)
            return row.storage_key, row.media_type, row.original_filename
