from uuid import UUID

from sqlalchemy import or_, select

from app.models.classroom import ClassroomAssignment
from app.models.classroom_classwork import ClassroomContentItem, ClassroomResource, ClassroomSection
from app.models.enums import AssignmentStatus


class ClassworkRepository:
    def __init__(self, session):
        self.session = session

    async def sections(self, classroom_id: UUID):
        return list(
            await self.session.scalars(
                select(ClassroomSection)
                .where(ClassroomSection.classroom_id == classroom_id)
                .order_by(ClassroomSection.position, ClassroomSection.id)
            )
        )

    async def items(self, classroom_id: UUID):
        return list(
            await self.session.scalars(
                select(ClassroomContentItem)
                .where(ClassroomContentItem.classroom_id == classroom_id)
                .order_by(ClassroomContentItem.position, ClassroomContentItem.id)
            )
        )

    async def snapshot(self, classroom_id: UUID, *, staff: bool):
        sections = await self.sections(classroom_id)
        if not staff:
            sections = [section for section in sections if section.status == "PUBLISHED"]
        items_query = select(ClassroomContentItem).where(
            ClassroomContentItem.classroom_id == classroom_id
        )
        if not staff:
            items_query = items_query.where(
                or_(
                    ClassroomContentItem.section_id.is_(None),
                    ClassroomContentItem.section_id.in_([section.id for section in sections]),
                ),
                or_(
                    ClassroomContentItem.resource_id.in_(
                        select(ClassroomResource.id).where(ClassroomResource.status == "PUBLISHED")
                    ),
                    ClassroomContentItem.assignment_id.in_(
                        select(ClassroomAssignment.id).where(
                            ClassroomAssignment.status == AssignmentStatus.ACTIVE
                        )
                    ),
                ),
            )
        items = list(
            await self.session.scalars(
                items_query.order_by(ClassroomContentItem.position, ClassroomContentItem.id)
            )
        )
        resources = list(
            await self.session.scalars(
                select(ClassroomResource)
                .where(
                    ClassroomResource.classroom_id == classroom_id,
                    ClassroomResource.id.in_(
                        [item.resource_id for item in items if item.resource_id]
                    ),
                )
                .order_by(ClassroomResource.created_at, ClassroomResource.id)
            )
        )
        return sections, resources, items

    async def resource(self, classroom_id: UUID, resource_id: UUID, *, staff: bool):
        query = select(ClassroomResource).where(
            ClassroomResource.id == resource_id, ClassroomResource.classroom_id == classroom_id
        )
        if not staff:
            query = (
                query.join(
                    ClassroomContentItem, ClassroomContentItem.resource_id == ClassroomResource.id
                )
                .outerjoin(ClassroomSection, ClassroomSection.id == ClassroomContentItem.section_id)
                .where(
                    ClassroomResource.status == "PUBLISHED",
                    or_(
                        ClassroomContentItem.section_id.is_(None),
                        ClassroomSection.status == "PUBLISHED",
                    ),
                )
            )
        return await self.session.scalar(query)
