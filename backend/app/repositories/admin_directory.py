from uuid import UUID

from sqlalchemy import distinct, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Classroom, ClassroomMembership, User
from app.models.enums import UserRole
from app.schemas.admin_directory import DirectoryRole


def _search_pattern(search: str | None) -> str | None:
    normalized = search.strip().casefold() if search else ""
    if not normalized:
        return None
    # Treat SQL wildcard characters as literal search text.
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _person_statement(role: DirectoryRole):
    if role == UserRole.TEACHER:
        classrooms = (
            select(func.count(Classroom.id))
            .where(Classroom.teacher_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
    else:
        classrooms = (
            select(func.count(distinct(ClassroomMembership.classroom_id)))
            .where(ClassroomMembership.user_id == User.id, ClassroomMembership.left_at.is_(None))
            .correlate(User)
            .scalar_subquery()
        )
    return select(
        User.id, User.display_name, User.role, User.is_active, classrooms.label("classroom_count")
    ).where(User.role == role)


class AdminDirectoryRepository:
    """Read-only, bounded discovery queries without private account/profile fields."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def people(
        self, *, role: DirectoryRole, search: str | None, offset: int, limit: int
    ):
        filters = [User.role == role]
        pattern = _search_pattern(search)
        if pattern:
            name_matches = func.lower(User.display_name).like(pattern, escape="\\")
            if role == UserRole.TEACHER:
                classroom_matches = exists(
                    select(Classroom.id).where(
                        Classroom.teacher_id == User.id,
                        func.lower(Classroom.name).like(pattern, escape="\\"),
                    )
                )
                filters.append(or_(name_matches, classroom_matches))
            else:
                filters.append(name_matches)
        total = int(await self.session.scalar(select(func.count(User.id)).where(*filters)) or 0)
        statement = (
            _person_statement(role)
            .where(*filters[1:])
            .order_by(func.lower(User.display_name), User.id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).mappings().all()
        return total, rows

    async def person(self, person_id: UUID, *, role: DirectoryRole):
        statement = _person_statement(role).where(User.id == person_id)
        return (await self.session.execute(statement)).mappings().one_or_none()

    async def classrooms(
        self,
        *,
        teacher_id: UUID | None,
        student_id: UUID | None,
        search: str | None,
        offset: int,
        limit: int,
    ):
        owner = aliased(User, name="owner")
        filters = []
        if teacher_id:
            filters.append(Classroom.teacher_id == teacher_id)
        if student_id:
            filters.append(
                exists(
                    select(ClassroomMembership.id)
                    .join(User, User.id == ClassroomMembership.user_id)
                    .where(
                        ClassroomMembership.classroom_id == Classroom.id,
                        ClassroomMembership.user_id == student_id,
                        ClassroomMembership.left_at.is_(None),
                        User.role != UserRole.ADMIN,
                    )
                )
            )
        pattern = _search_pattern(search)
        if pattern:
            filters.append(
                or_(
                    func.lower(Classroom.name).like(pattern, escape="\\"),
                    func.lower(owner.display_name).like(pattern, escape="\\"),
                )
            )
        total = int(
            await self.session.scalar(
                select(func.count(Classroom.id))
                .join(owner, owner.id == Classroom.teacher_id)
                .where(*filters)
            )
            or 0
        )
        enrolled_count = (
            select(func.count(distinct(ClassroomMembership.user_id)))
            .join(User, User.id == ClassroomMembership.user_id)
            .where(
                ClassroomMembership.classroom_id == Classroom.id,
                ClassroomMembership.left_at.is_(None),
                User.role != UserRole.ADMIN,
            )
            .correlate(Classroom)
            .scalar_subquery()
        )
        statement = (
            select(
                Classroom.id,
                Classroom.name,
                Classroom.status,
                owner.id.label("teacher_id"),
                owner.display_name.label("teacher_name"),
                enrolled_count.label("enrolled_student_count"),
            )
            .join(owner, owner.id == Classroom.teacher_id)
            .where(*filters)
            .order_by(Classroom.created_at.desc(), Classroom.id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).mappings().all()
        return total, rows
