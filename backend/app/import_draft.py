"""Import OCR-ready JSON as a new, unpublished Builder draft.

Run: uv run python -m app.import_draft path/to/manifest.json --owner-user-id ADMIN_UUID
"""

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.core.database import SessionFactory
from app.core.exceptions import AppError
from app.models import User
from app.models.enums import UserRole
from app.services.draft_import import DraftImportService, load_manifest


async def _run(path: Path, owner_user_id: UUID) -> int:
    manifest = load_manifest(path)
    async with SessionFactory() as session:
        async with session.begin():
            actor = await session.scalar(
                select(User).where(
                    User.id == owner_user_id, User.role == UserRole.ADMIN, User.is_active.is_(True)
                )
            )
            if actor is None:
                raise AppError(
                    "ADMIN_REQUIRED", "Choose an active administrator as import owner.", 403
                )
        result = await DraftImportService(session, actor=actor).import_manifest(
            manifest,
            path.resolve().parent,  # noqa: ASYNC240
        )
    print(f"Imported draft:\n  Test: {result.title}\n  Version: 1\n  Status: DRAFT")
    for module, (units, groups, questions) in result.counts.items():
        label = {"READING": "passages", "LISTENING": "sections", "WRITING": "tasks"}[module]
        unit_label = label[:-1] if units == 1 else label
        print(f"\n{module.title()}:\n  {units} {unit_label}")
        if module != "WRITING":
            print(f"  {groups} groups\n  {questions} questions")
        if module == "LISTENING":
            listening = next(item for item in manifest.modules if item.type == "LISTENING")
            print(f"  Audio: {'attached' if listening.audio else 'not attached'}")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    print(f"\nBuilder:\n  /admin/tests/{result.test_id}/versions/{result.version_id}/edit")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a structured IELTS draft")
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--owner-user-id",
        type=UUID,
        required=True,
        help="Active administrator who owns this new import",
    )
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args.manifest, args.owner_user_id))
    except AppError as exc:
        parser.exit(1, f"Import failed: {exc.message}\n")


if __name__ == "__main__":
    raise SystemExit(main())
