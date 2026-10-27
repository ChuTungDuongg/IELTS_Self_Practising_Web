from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ClassroomStatus

DirectoryRole = Literal["TEACHER", "USER"]


class DirectoryPerson(BaseModel):
    id: UUID
    display_name: str
    role: DirectoryRole
    is_active: bool
    classroom_count: int = Field(ge=0)


class DirectoryPeoplePage(BaseModel):
    items: list[DirectoryPerson]
    total: int
    offset: int
    limit: int


class DirectoryTeacher(BaseModel):
    id: UUID
    display_name: str


class DirectoryClassroom(BaseModel):
    id: UUID
    name: str
    status: ClassroomStatus
    teacher: DirectoryTeacher
    enrolled_student_count: int = Field(ge=0)


class DirectoryClassroomsPage(BaseModel):
    items: list[DirectoryClassroom]
    total: int
    offset: int
    limit: int
