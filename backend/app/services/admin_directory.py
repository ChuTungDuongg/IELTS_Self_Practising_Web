from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.repositories.admin_directory import AdminDirectoryRepository
from app.schemas.admin_directory import (
    DirectoryClassroom,
    DirectoryClassroomsPage,
    DirectoryPeoplePage,
    DirectoryPerson,
    DirectoryRole,
    DirectoryTeacher,
)


class AdminDirectoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = AdminDirectoryRepository(session)

    async def people(
        self, *, role: DirectoryRole, search: str | None, offset: int, limit: int
    ) -> DirectoryPeoplePage:
        total, rows = await self.repository.people(
            role=role, search=search, offset=offset, limit=limit
        )
        return DirectoryPeoplePage(
            items=[DirectoryPerson.model_validate(row) for row in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def person(self, person_id: UUID, *, role: DirectoryRole) -> DirectoryPerson:
        row = await self.repository.person(person_id, role=role)
        if row is None:
            raise AppError("USER_NOT_FOUND", "The requested directory person does not exist.", 404)
        return DirectoryPerson.model_validate(row)

    async def classrooms(
        self,
        *,
        teacher_id: UUID | None,
        student_id: UUID | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> DirectoryClassroomsPage:
        total, rows = await self.repository.classrooms(
            teacher_id=teacher_id,
            student_id=student_id,
            search=search,
            offset=offset,
            limit=limit,
        )
        return DirectoryClassroomsPage(
            items=[
                DirectoryClassroom(
                    id=row["id"],
                    name=row["name"],
                    status=row["status"],
                    teacher=DirectoryTeacher(id=row["teacher_id"], display_name=row["teacher_name"]),
                    enrolled_student_count=row["enrolled_student_count"],
                )
                for row in rows
            ],
            total=total,
            offset=offset,
            limit=limit,
        )
