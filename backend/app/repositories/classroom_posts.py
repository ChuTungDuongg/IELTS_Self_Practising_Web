from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, literal, or_, select, tuple_, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClassroomAssignment, ClassroomMembership, User
from app.models.classroom_classwork import (
    ClassroomContentItem,
    ClassroomResource,
    ClassroomSection,
)
from app.models.classroom_posts import ClassroomComment, ClassroomPost, ClassroomPostResource
from app.models.enums import AssignmentStatus


class ClassroomPostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def post(self, classroom_id: UUID, post_id: UUID):
        return await self.session.scalar(
            select(ClassroomPost)
            .where(ClassroomPost.classroom_id == classroom_id, ClassroomPost.id == post_id)
            .execution_options(populate_existing=True)
        )

    async def comment(self, classroom_id: UUID, comment_id: UUID):
        return await self.session.scalar(
            select(ClassroomComment)
            .join(ClassroomPost, ClassroomPost.id == ClassroomComment.post_id)
            .where(ClassroomPost.classroom_id == classroom_id, ClassroomComment.id == comment_id)
            .execution_options(populate_existing=True)
        )

    async def resource_visibility(self, classroom_id: UUID, ids: list[UUID]):
        if not ids:
            return []
        return (
            await self.session.execute(
                select(ClassroomResource.id, ClassroomResource.status, ClassroomSection.status)
                .outerjoin(
                    ClassroomContentItem,
                    ClassroomContentItem.resource_id == ClassroomResource.id,
                )
                .outerjoin(ClassroomSection, ClassroomSection.id == ClassroomContentItem.section_id)
                .where(
                    ClassroomResource.classroom_id == classroom_id, ClassroomResource.id.in_(ids)
                )
            )
        ).all()

    async def resource_ids(self, post_ids: list[UUID], *, staff: bool):
        grouped: dict[UUID, list[UUID]] = {post_id: [] for post_id in post_ids}
        if not post_ids:
            return grouped
        query = (
            select(ClassroomPostResource.post_id, ClassroomPostResource.resource_id)
            .join(ClassroomResource, ClassroomResource.id == ClassroomPostResource.resource_id)
            .outerjoin(
                ClassroomContentItem, ClassroomContentItem.resource_id == ClassroomResource.id
            )
            .outerjoin(ClassroomSection, ClassroomSection.id == ClassroomContentItem.section_id)
            .where(ClassroomPostResource.post_id.in_(post_ids))
        )
        if not staff:
            query = query.where(
                ClassroomResource.status == "PUBLISHED",
                or_(ClassroomSection.id.is_(None), ClassroomSection.status == "PUBLISHED"),
            )
        for post_id, resource_id in await self.session.execute(
            query.order_by(ClassroomPostResource.resource_id)
        ):
            grouped[post_id].append(resource_id)
        return grouped

    async def replace_resources(self, post_id: UUID, ids: list[UUID]):
        await self.session.execute(
            delete(ClassroomPostResource).where(ClassroomPostResource.post_id == post_id)
        )
        self.session.add_all(
            ClassroomPostResource(post_id=post_id, resource_id=resource_id) for resource_id in ids
        )

    async def feed_keys(
        self,
        classroom_id: UUID,
        *,
        staff: bool,
        status: str | None,
        cursor: tuple[bool, datetime, str, UUID] | None,
        limit: int,
        content_kind: str | None = None,
    ):
        """A single bounded UNION keeps assignment identity/lifecycle canonical."""
        posts = select(
            ClassroomPost.id.label("id"),
            ClassroomPost.kind.label("kind"),
            ClassroomPost.created_at.label("created_at"),
            ClassroomPost.pinned.label("pinned"),
        ).where(ClassroomPost.classroom_id == classroom_id)
        if status is not None:
            posts = posts.where(ClassroomPost.status == status)
        elif staff:
            posts = posts.where(ClassroomPost.status != "ARCHIVED")
        else:
            posts = posts.where(ClassroomPost.status == "PUBLISHED")
        assignments = select(
            ClassroomAssignment.id.label("id"),
            literal("ASSIGNMENT_ACTIVITY").label("kind"),
            ClassroomAssignment.created_at.label("created_at"),
            literal(False).label("pinned"),
        ).where(ClassroomAssignment.classroom_id == classroom_id)
        if status == "DRAFT":
            assignments = assignments.where(literal(False))
        else:
            assignments = assignments.where(
                ClassroomAssignment.status
                == (AssignmentStatus.ARCHIVED if status == "ARCHIVED" else AssignmentStatus.ACTIVE)
            )
        feed = union_all(posts, assignments).subquery("classroom_feed")
        query = select(feed)
        if content_kind is not None:
            query = query.where(feed.c.kind == content_kind)
        if cursor is not None:
            query = query.where(
                tuple_(feed.c.pinned, feed.c.created_at, feed.c.kind, feed.c.id) < tuple_(*cursor)
            )
        return (
            await self.session.execute(
                query.order_by(
                    feed.c.pinned.desc(),
                    feed.c.created_at.desc(),
                    feed.c.kind.desc(),
                    feed.c.id.desc(),
                ).limit(limit + 1)
            )
        ).all()

    async def posts_with_authors(
        self, ids: list[UUID], *, classroom_id: UUID, statuses: list[str] | None
    ):
        if not ids:
            return []
        query = (
            select(ClassroomPost, User)
            .join(User, User.id == ClassroomPost.author_id)
            .where(ClassroomPost.classroom_id == classroom_id, ClassroomPost.id.in_(ids))
            .execution_options(populate_existing=True)
        )
        if statuses is not None:
            query = query.where(ClassroomPost.status.in_(statuses))
        return (await self.session.execute(query)).all()

    async def assignments_with_authors(self, ids: list[UUID]):
        if not ids:
            return []
        return (
            await self.session.execute(
                select(ClassroomAssignment, User)
                .join(User, User.id == ClassroomAssignment.created_by_user_id)
                .where(ClassroomAssignment.id.in_(ids))
            )
        ).all()

    async def comment_counts(self, post_ids: list[UUID]):
        if not post_ids:
            return {}
        return dict(
            (
                await self.session.execute(
                    select(ClassroomComment.post_id, func.count())
                    .where(
                        ClassroomComment.post_id.in_(post_ids), ClassroomComment.state == "VISIBLE"
                    )
                    .group_by(ClassroomComment.post_id)
                )
            ).all()
        )

    async def comments(self, post_id: UUID, *, cursor: tuple[datetime, UUID] | None, limit: int):
        query = (
            select(ClassroomComment, User)
            .join(User, User.id == ClassroomComment.author_id)
            .where(ClassroomComment.post_id == post_id)
        )
        if cursor is not None:
            query = query.where(
                tuple_(ClassroomComment.created_at, ClassroomComment.id) > tuple_(*cursor)
            )
        return (
            await self.session.execute(
                query.order_by(ClassroomComment.created_at, ClassroomComment.id).limit(limit + 1)
            )
        ).all()

    async def notification_recipients(self, classroom_id: UUID, owner_id: UUID):
        return list(
            await self.session.scalars(
                select(ClassroomMembership.user_id)
                .join(User, User.id == ClassroomMembership.user_id)
                .where(
                    ClassroomMembership.classroom_id == classroom_id,
                    ClassroomMembership.left_at.is_(None),
                    ClassroomMembership.user_id != owner_id,
                    User.is_active.is_(True),
                )
                .order_by(ClassroomMembership.user_id)
            )
        )
