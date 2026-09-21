import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.core.config import get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.schemas.transfer import TransferExportRequest, TransferImportResult
from app.services.transfer import TransferService

router = APIRouter(prefix="/transfer", tags=["transfer"])


def _remove(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.post("/export", response_class=FileResponse)
async def export_tests(
    body: TransferExportRequest,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    handle = tempfile.NamedTemporaryFile(prefix="ielts-transfer-", suffix=".zip", delete=False)
    path = Path(handle.name)
    handle.close()
    try:
        await TransferService(session, get_settings()).export(body.test_ids, path)
    except Exception:
        _remove(path)
        raise
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"ielts-tests-{date.today().isoformat()}.zip",
        background=BackgroundTask(_remove, path),
    )


@router.post("/import", response_model=TransferImportResult)
async def import_tests(
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
) -> TransferImportResult:
    filename = Path((file.filename or "").replace("\\", "/")).name
    if Path(filename).suffix.lower() != ".zip":
        raise AppError("TRANSFER_FILE_INVALID", "Choose a ZIP test package.", 422)
    settings = get_settings()
    maximum = settings.max_transfer_zip_mb * 1024 * 1024
    with tempfile.TemporaryDirectory(prefix="ielts-transfer-import-") as temporary:
        root = Path(temporary)
        archive_path = root / "package.zip"
        size = 0
        with archive_path.open("xb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > maximum:
                    raise AppError(
                        "TRANSFER_FILE_TOO_LARGE", "The ZIP exceeds the transfer size limit.", 413
                    )
                destination.write(chunk)
        if size == 0:
            raise AppError("TRANSFER_FILE_INVALID", "The uploaded ZIP is empty.", 422)
        service = TransferService(session, settings)
        package = service.validate_archive(archive_path, root)
        return await service.import_package(package)
