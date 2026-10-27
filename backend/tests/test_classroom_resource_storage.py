from io import BytesIO

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.schemas.classroom_classwork import ResourceCreate
from app.storage.classroom import ClassroomResourceStorage


def test_resource_upload_uses_generated_key_and_signature(tmp_path):
    storage = ClassroomResourceStorage(tmp_path)
    stored = storage.store_resource(
        BytesIO(b"%PDF-1.7\nfictional lesson"), "lesson.pdf", "application/pdf"
    )
    assert stored.relative_path.startswith("classroom-resources/")
    assert "lesson" not in stored.relative_path
    assert storage.resolve(stored.relative_path).read_bytes().startswith(b"%PDF-")


@pytest.mark.parametrize(
    "name,mime,content",
    [
        ("../lesson.pdf", "application/pdf", b"%PDF-1.7"),
        ("C:\\lesson.pdf", "application/pdf", b"%PDF-1.7"),
        ("lesson.html", "text/html", b"<script>alert(1)</script>"),
        ("lesson.pdf", "application/pdf", b"<html>fake PDF</html>"),
        ("lesson.svg", "image/svg+xml", b"<svg/>"),
        ("lesson.png", "image/png", b"not an image"),
    ],
)
def test_resource_upload_rejects_unsafe_files_without_orphans(tmp_path, name, mime, content):
    with pytest.raises(AppError):
        ClassroomResourceStorage(tmp_path).store_resource(BytesIO(content), name, mime)
    assert not list(tmp_path.rglob("*.*"))


def test_resource_upload_is_bounded(tmp_path):
    with pytest.raises(AppError):
        ClassroomResourceStorage(tmp_path).store_resource(
            BytesIO(b"a" * 30), "lesson.txt", "text/plain", max_bytes=20
        )
    assert not list(tmp_path.rglob("*.*"))


def test_resource_image_limit_is_independent_of_ai_image_limit(tmp_path):
    content = b"\x89PNG\r\n\x1a\n" + b"\x00" * (11 * 1024 * 1024)
    stored = ClassroomResourceStorage(tmp_path).store_resource(
        BytesIO(content), "lesson.png", "image/png"
    )
    assert stored.size == len(content)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,test",
        "//example.com",
        "https://user:secret@example.com",
    ],
)
def test_resource_links_reject_unsafe_protocols_and_credentials(url):
    with pytest.raises(ValidationError):
        ResourceCreate(title="Strategy", kind="LINK", url=url)


def test_resource_rejects_irrelevant_content():
    with pytest.raises(ValidationError):
        ResourceCreate(title="Strategy", kind="TEXT", body="Notes", url="https://example.com")
