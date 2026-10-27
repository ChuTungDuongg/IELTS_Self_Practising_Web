import base64
import binascii
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Classroom, User
from app.models.classroom_posts import ClassroomComment, ClassroomPost
from app.models.enums import NotificationEntityType, NotificationType, UserRole
from app.repositories.classroom_posts import ClassroomPostRepository
from app.schemas.classroom_posts import (
    CommentCreate,
    CommentPage,
    CommentResponse,
    CommentUpdate,
    ContentStatus,
    FeedEntry,
    FeedPage,
    PostCreate,
    PostUpdate,
)
from app.services.classroom_content_access import ContentAccess
from app.services.notifications import NotificationService


class _FeedCursor(BaseModel):
    version: Literal[1] = 1
    classroom_id: UUID
    status: ContentStatus | None
    pinned: bool = Field(strict=True)
    created_at: AwareDatetime
    kind: Literal["ANNOUNCEMENT", "DISCUSSION", "ASSIGNMENT_ACTIVITY"]
    id: UUID
    model_config = {"extra": "forbid"}


class _CommentCursor(BaseModel):
    version: Literal[1] = 1
    post_id: UUID
    created_at: AwareDatetime
    id: UUID
    model_config = {"extra": "forbid"}


def _encode_cursor(value: BaseModel) -> str:
    return base64.urlsafe_b64encode(value.model_dump_json().encode()).decode().rstrip("=")


def _decode_cursor(value: str, schema):
    try:
        if len(value) > 2048:
            raise ValueError("Cursor exceeds maximum length")
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        return schema.model_validate_json(raw)
    except (ValueError, ValidationError, binascii.Error) as error:
        raise AppError("INVALID_CURSOR", "This pagination cursor is invalid.", 422) from error


class ClassroomPostService:
    def __init__(self, session: AsyncSession, actor: User):
        self.session = session
        self.access = ContentAccess(session, actor)
        self.repository = ClassroomPostRepository(session)
        self.notifications = NotificationService(session)

    async def _post(self, room: Classroom, post_id: UUID, *, published=False):
        post = await self.repository.post(room.id, post_id)
        if post is None or (
            (published or not self.access.staff(room)) and post.status != "PUBLISHED"
        ):
            raise AppError("CLASSROOM_POST_NOT_FOUND", "The classroom post does not exist.", 404)
        return post

    async def _validate_resources(self, room: Classroom, ids: list[UUID], *, published: bool):
        rows = await self.repository.resource_visibility(room.id, ids)
        if len(rows) != len(ids):
            raise AppError(
                "CLASSROOM_RESOURCE_NOT_FOUND", "A classroom resource does not exist.", 404
            )
        if published and any(
            status != "PUBLISHED" or (section_status is not None and section_status != "PUBLISHED")
            for _, status, section_status in rows
        ):
            raise AppError(
                "CLASSROOM_RESOURCE_NOT_PUBLISHED",
                "Published posts can reference only published resources in visible sections.",
                409,
            )

    async def _publish(self, room: Classroom, post: ClassroomPost, resource_ids: list[UUID]):
        await self._validate_resources(room, resource_ids, published=True)
        first_publication = post.published_at is None
        post.status = "PUBLISHED"
        if first_publication:
            post.published_at = datetime.now(UTC)
        await self.session.flush()
        if first_publication and post.kind == "ANNOUNCEMENT":
            for recipient in await self.repository.notification_recipients(
                room.id, room.teacher_id
            ):
                await self.notifications.create_once(
                    user_id=recipient,
                    type=NotificationType.CLASSROOM_ANNOUNCEMENT_PUBLISHED,
                    entity_type=NotificationEntityType.CLASSROOM_POST,
                    entity_id=post.id,
                    payload={
                        "classroom_id": str(room.id),
                        "classroom_name": room.name,
                        "post_title": post.title or "",
                    },
                )

    @staticmethod
    def _entry(post: ClassroomPost, author: User, *, count: int, resources: list[UUID]):
        return FeedEntry(
            id=post.id,
            kind=post.kind,
            title=post.title,
            body=post.body,
            status=post.status,
            pinned=post.pinned,
            locked=post.locked,
            author_id=post.author_id,
            author_name=author.display_name,
            author_role=author.role,
            created_at=post.created_at,
            updated_at=post.updated_at,
            published_at=post.published_at,
            comment_count=count,
            resource_ids=resources,
        )

    async def _present_post(self, room: Classroom, post: ClassroomPost):
        rows = await self.repository.posts_with_authors(
            [post.id],
            classroom_id=room.id,
            statuses=None if self.access.staff(room) else ["PUBLISHED"],
        )
        if not rows:
            raise AppError("CLASSROOM_POST_NOT_FOUND", "The classroom post does not exist.", 404)
        counts = await self.repository.comment_counts([post.id])
        resources = await self.repository.resource_ids([post.id], staff=self.access.staff(room))
        return self._entry(
            rows[0][0], rows[0][1], count=counts.get(post.id, 0), resources=resources[post.id]
        )

    async def feed(
        self,
        classroom_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: ContentStatus | None = None,
    ) -> FeedPage:
        if not 1 <= limit <= 100:
            raise AppError("INVALID_PAGE_SIZE", "Page size must be between 1 and 100.", 422)
        async with self.session.begin():
            room = await self.access.room(classroom_id)
            staff = self.access.staff(room)
            if status is not None and not staff:
                raise AppError(
                    "CLASSROOM_OWNERSHIP_REQUIRED", "Only staff may filter post status.", 403
                )
            position = None
            if cursor is not None:
                decoded = _decode_cursor(cursor, _FeedCursor)
                if decoded.classroom_id != classroom_id or decoded.status != status:
                    raise AppError("INVALID_CURSOR", "This cursor belongs to another feed.", 422)
                position = (decoded.pinned, decoded.created_at, decoded.kind, decoded.id)
            keys = await self.repository.feed_keys(
                classroom_id, staff=staff, status=status, cursor=position, limit=limit
            )
            selected = keys[:limit]
            post_ids = [key.id for key in selected if key.kind != "ASSIGNMENT_ACTIVITY"]
            assignment_ids = [key.id for key in selected if key.kind == "ASSIGNMENT_ACTIVITY"]
            visible_statuses = ["DRAFT", "PUBLISHED"] if staff else ["PUBLISHED"]
            if status is not None:
                visible_statuses = [status]
            post_rows = await self.repository.posts_with_authors(
                post_ids,
                classroom_id=room.id,
                statuses=visible_statuses,
            )
            counts = await self.repository.comment_counts(post_ids)
            resources = await self.repository.resource_ids(post_ids, staff=staff)
            entries = {
                ("POST", post.id): self._entry(
                    post, author, count=counts.get(post.id, 0), resources=resources[post.id]
                )
                for post, author in post_rows
            }
            for assignment, author in await self.repository.assignments_with_authors(
                assignment_ids
            ):
                entries[("ASSIGNMENT_ACTIVITY", assignment.id)] = FeedEntry(
                    id=assignment.id,
                    kind="ASSIGNMENT_ACTIVITY",
                    title=assignment.title,
                    body=assignment.note or "",
                    status="PUBLISHED" if assignment.status == "ACTIVE" else "ARCHIVED",
                    pinned=False,
                    locked=True,
                    author_id=assignment.created_by_user_id,
                    author_name=author.display_name,
                    author_role=author.role,
                    created_at=assignment.created_at,
                    updated_at=assignment.archived_at or assignment.created_at,
                    published_at=assignment.created_at,
                    comment_count=0,
                    resource_ids=[],
                    assignment_id=assignment.id,
                )
            next_cursor = None
            if len(keys) > limit:
                last = selected[-1]
                next_cursor = _encode_cursor(
                    _FeedCursor(
                        classroom_id=room.id,
                        status=status,
                        pinned=last.pinned,
                        created_at=last.created_at,
                        kind=last.kind,
                        id=last.id,
                    )
                )
            ordered_entries = []
            for key in selected:
                namespace = "ASSIGNMENT_ACTIVITY" if key.kind == "ASSIGNMENT_ACTIVITY" else "POST"
                entry = entries.get((namespace, key.id))
                if entry is not None:
                    ordered_entries.append(entry)
            return FeedPage(items=ordered_entries, next_cursor=next_cursor)

    async def get(self, classroom_id: UUID, post_id: UUID) -> FeedEntry:
        async with self.session.begin():
            room = await self.access.room(classroom_id)
            post = await self._post(room, post_id)
            return await self._present_post(room, post)

    async def create(self, classroom_id: UUID, data: PostCreate) -> FeedEntry:
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            await self._validate_resources(
                room, data.resource_ids, published=data.status == "PUBLISHED"
            )
            post = ClassroomPost(
                classroom_id=room.id,
                author_id=self.access.actor.id,
                kind=data.kind,
                title=data.title,
                body=data.body,
                status="DRAFT",
            )
            self.session.add(post)
            await self.session.flush()
            await self.repository.replace_resources(post.id, data.resource_ids)
            if data.status == "PUBLISHED":
                await self._publish(room, post, data.resource_ids)
            await self.session.flush()
            await self.session.refresh(post)
            return await self._present_post(room, post)

    async def update(self, classroom_id: UUID, post_id: UUID, data: PostUpdate) -> FeedEntry:
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True, owner=True)
            post = await self._post(room, post_id)
            changes = data.model_dump(exclude_unset=True)
            current_resources = (await self.repository.resource_ids([post.id], staff=True))[post.id]
            resources = changes.pop("resource_ids", current_resources)
            target_status = changes.get("status", post.status)
            publishing = target_status == "PUBLISHED" and post.status != "PUBLISHED"
            await self._validate_resources(
                room,
                resources,
                published=target_status == "PUBLISHED"
                and (publishing or data.resource_ids is not None),
            )
            for field, value in changes.items():
                setattr(post, field, value)
            if data.resource_ids is not None:
                await self.repository.replace_resources(post.id, resources)
            if publishing:
                await self._publish(room, post, resources)
            await self.session.flush()
            await self.session.refresh(post)
            return await self._present_post(room, post)

    async def publish(self, classroom_id: UUID, post_id: UUID) -> FeedEntry:
        return await self.update(classroom_id, post_id, PostUpdate(status="PUBLISHED"))

    async def archive(self, classroom_id: UUID, post_id: UUID) -> FeedEntry:
        return await self.update(classroom_id, post_id, PostUpdate(status="ARCHIVED", pinned=False))

    @staticmethod
    def _comment_response(comment: ClassroomComment, author: User):
        return CommentResponse(
            id=comment.id,
            post_id=comment.post_id,
            author_id=comment.author_id,
            author_name=author.display_name,
            body=comment.body if comment.state == "VISIBLE" else "",
            state=comment.state,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )

    async def comments(
        self, classroom_id: UUID, post_id: UUID, *, cursor: str | None = None, limit: int = 20
    ) -> CommentPage:
        if not 1 <= limit <= 100:
            raise AppError("INVALID_PAGE_SIZE", "Page size must be between 1 and 100.", 422)
        async with self.session.begin():
            room = await self.access.room(classroom_id)
            await self._post(room, post_id)
            position = None
            if cursor is not None:
                decoded = _decode_cursor(cursor, _CommentCursor)
                if decoded.post_id != post_id:
                    raise AppError(
                        "INVALID_CURSOR", "This cursor belongs to another discussion.", 422
                    )
                position = (decoded.created_at, decoded.id)
            rows = await self.repository.comments(post_id, cursor=position, limit=limit)
            selected = rows[:limit]
            next_cursor = None
            if len(rows) > limit:
                last = selected[-1][0]
                next_cursor = _encode_cursor(
                    _CommentCursor(post_id=post_id, created_at=last.created_at, id=last.id)
                )
            return CommentPage(
                items=[self._comment_response(comment, author) for comment, author in selected],
                next_cursor=next_cursor,
            )

    async def create_comment(
        self, classroom_id: UUID, post_id: UUID, data: CommentCreate
    ) -> CommentResponse:
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True)
            await self.access.can_comment(room)
            post = await self._post(room, post_id, published=True)
            if post.locked:
                raise AppError("CLASSROOM_POST_LOCKED", "This discussion is locked.", 409)
            comment = ClassroomComment(
                post_id=post.id, author_id=self.access.actor.id, body=data.body
            )
            self.session.add(comment)
            await self.session.flush()
            await self.session.refresh(comment)
            return self._comment_response(comment, self.access.actor)

    async def _comment(self, room: Classroom, comment_id: UUID):
        comment = await self.repository.comment(room.id, comment_id)
        if comment is None:
            raise AppError(
                "CLASSROOM_COMMENT_NOT_FOUND", "The classroom comment does not exist.", 404
            )
        await self._post(room, comment.post_id, published=True)
        return comment

    async def update_comment(
        self, classroom_id: UUID, comment_id: UUID, data: CommentUpdate
    ) -> CommentResponse:
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True)
            await self.access.can_comment(room)
            comment = await self._comment(room, comment_id)
            if comment.author_id != self.access.actor.id:
                raise AppError(
                    "COMMENT_OWNERSHIP_REQUIRED", "Only the author may edit this comment.", 403
                )
            if comment.state != "VISIBLE":
                raise AppError(
                    "CLASSROOM_COMMENT_REMOVED", "This comment is no longer editable.", 409
                )
            comment.body = data.body
            await self.session.flush()
            await self.session.refresh(comment)
            return self._comment_response(comment, self.access.actor)

    async def delete_comment(self, classroom_id: UUID, comment_id: UUID) -> CommentResponse:
        async with self.session.begin():
            room = await self.access.room(classroom_id, mutation=True)
            await self.access.can_comment(room)
            comment = await self._comment(room, comment_id)
            own_comment = comment.author_id == self.access.actor.id
            owner = (
                self.access.actor.role == UserRole.TEACHER
                and room.teacher_id == self.access.actor.id
            )
            if not own_comment and not owner:
                raise AppError(
                    "COMMENT_OWNERSHIP_REQUIRED",
                    "Only the author or teacher owner may remove this comment.",
                    403,
                )
            if comment.state == "VISIBLE":
                comment.state = "RETRACTED" if own_comment else "MODERATED"
            await self.session.flush()
            await self.session.refresh(comment)
            author = await self.session.get(User, comment.author_id)
            return self._comment_response(comment, author)
