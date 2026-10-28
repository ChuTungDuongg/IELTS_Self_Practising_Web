from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.schemas.classroom_classwork import (
    AssignmentPlacement,
    ClassworkResponse,
    ItemReorderRequest,
    ReorderRequest,
    ResourceCreate,
    ResourceResponse,
    ResourceUpdate,
    SectionCreate,
    SectionResponse,
    SectionUpdate,
)
from app.services.classroom_classwork import ClassworkService
from app.storage.delivery import storage_response
from app.storage.factory import get_asset_storage

router = APIRouter(prefix="/classrooms/{classroom_id}", tags=["classroom-classwork"])


@router.delete("/sections/{section_id}", response_model=ClassworkResponse)
async def delete_section(
    classroom_id: UUID,
    section_id: UUID,
    actor: CurrentUser,
    expected_revision: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).delete_section(
        classroom_id, section_id, expected_revision
    )


@router.delete("/resources/{resource_id}", response_model=ClassworkResponse)
async def delete_resource(
    classroom_id: UUID,
    resource_id: UUID,
    actor: CurrentUser,
    expected_revision: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).delete_resource(
        classroom_id, resource_id, expected_revision
    )


@router.delete("/items/{item_id}", response_model=ClassworkResponse)
async def remove_assignment(
    classroom_id: UUID,
    item_id: UUID,
    actor: CurrentUser,
    expected_revision: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).remove_assignment(
        classroom_id, item_id, expected_revision
    )


@router.get("/classwork", response_model=ClassworkResponse)
async def classwork(
    classroom_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    return await ClassworkService(session, actor).get(classroom_id)


@router.delete("/assignments/{assignment_id}/classwork", response_model=ClassworkResponse)
async def remove_assignment_reference(
    classroom_id: UUID,
    assignment_id: UUID,
    actor: CurrentUser,
    expected_revision: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).remove_assignment_reference(
        classroom_id, assignment_id, expected_revision
    )


@router.get("/sections", response_model=dict[str, list[SectionResponse]])
async def sections(
    classroom_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    data = await ClassworkService(session, actor).get(classroom_id)
    return {"items": data.sections}


@router.post("/sections", response_model=SectionResponse, status_code=201)
async def create_section(
    classroom_id: UUID,
    body: SectionCreate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).create_section(classroom_id, body)


@router.patch("/sections/{section_id}", response_model=SectionResponse)
async def update_section(
    classroom_id: UUID,
    section_id: UUID,
    body: SectionUpdate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).update_section(classroom_id, section_id, body)


@router.post("/sections/reorder", response_model=ClassworkResponse)
async def reorder_sections(
    classroom_id: UUID,
    body: ReorderRequest,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).reorder_sections(classroom_id, body)


@router.get("/resources", response_model=dict[str, list[ResourceResponse]])
async def resources(
    classroom_id: UUID, actor: CurrentUser, session: AsyncSession = Depends(get_session)
):
    data = await ClassworkService(session, actor).get(classroom_id)
    return {"items": data.resources}


@router.post("/resources", response_model=ResourceResponse, status_code=201)
async def create_resource(
    classroom_id: UUID,
    body: ResourceCreate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).create_resource(classroom_id, body)


@router.post("/resources/upload", response_model=ResourceResponse, status_code=201)
async def upload_resource(
    classroom_id: UUID,
    actor: CurrentUser,
    file: UploadFile = File(),
    title: str = Form(min_length=1, max_length=240),
    description: str | None = Form(default=None, max_length=4000),
    status: Literal["DRAFT", "PUBLISHED"] = Form(default="DRAFT"),
    section_id: UUID | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = SectionCreate(title=title, description=description, status=status)
    except ValidationError as error:
        raise AppError(
            "RESOURCE_INPUT_INVALID", "Resource title or description is invalid.", 422
        ) from error
    return await ClassworkService(session, actor).upload(classroom_id, file, data, section_id)


@router.get("/resources/{resource_id}", response_model=ResourceResponse)
async def resource_detail(
    classroom_id: UUID,
    resource_id: UUID,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).get_resource(classroom_id, resource_id)


@router.patch("/resources/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    classroom_id: UUID,
    resource_id: UUID,
    body: ResourceUpdate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).update_resource(classroom_id, resource_id, body)


@router.get("/resources/{resource_id}/file", response_class=StreamingResponse)
async def resource_file(
    classroom_id: UUID,
    resource_id: UUID,
    request: Request,
    actor: CurrentUser,
    inline: bool = False,
    session: AsyncSession = Depends(get_session),
):
    key, media_type, filename = await ClassworkService(session, actor).file(
        classroom_id, resource_id
    )
    disposition = (
        "inline"
        if inline and media_type in {"application/pdf", "image/png", "image/jpeg", "image/webp"}
        else "attachment"
    )
    return await storage_response(
        request,
        get_asset_storage(get_settings()),
        key,
        media_type=media_type,
        filename=filename,
        disposition=disposition,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
        },
    )


@router.post("/items", response_model=ClassworkResponse, status_code=201)
async def place_assignment(
    classroom_id: UUID,
    body: AssignmentPlacement,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).place_assignment(classroom_id, body)


@router.post("/items/reorder", response_model=ClassworkResponse)
async def reorder_items(
    classroom_id: UUID,
    body: ItemReorderRequest,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await ClassworkService(session, actor).reorder_items(classroom_id, body)
