"""Atomic revision check for an already locked Builder resource."""

from typing import Protocol

from app.core.exceptions import AppError


class Revisioned(Protocol):
    revision: int


def advance_revision(resource: Revisioned, expected_revision: int) -> None:
    if resource.revision != expected_revision:
        raise AppError(
            "DRAFT_REVISION_CONFLICT",
            "This draft content was changed elsewhere. Reload the latest version before saving.",
            409,
        )
    resource.revision += 1
