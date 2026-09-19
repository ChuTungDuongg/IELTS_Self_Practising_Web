"""move Listening audio ownership to the module

Revision ID: 20260919_0004
Revises: 20260919_0003
Create Date: 2026-09-19
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0004"
down_revision: str | None = "20260919_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _resolve_legacy_audio_ids(audio_ids: Iterable[Any | None]) -> Any | None:
    distinct = {audio_id for audio_id in audio_ids if audio_id is not None}
    if len(distinct) > 1:
        raise RuntimeError(
            "Cannot migrate Listening module with multiple distinct audio assets; "
            "resolve the legacy Part audio conflict before retrying."
        )
    return next(iter(distinct), None)


def upgrade() -> None:
    op.add_column("test_modules", sa.Column("audio_asset_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_test_modules_audio_asset_id_assets",
        "test_modules",
        "assets",
        ["audio_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    connection = op.get_bind()
    legacy_rows = connection.execute(
        sa.text(
            "SELECT module_id, audio_asset_id FROM listening_parts "
            "ORDER BY module_id, order_index"
        )
    ).all()
    by_module: dict[Any, list[Any | None]] = defaultdict(list)
    for module_id, audio_asset_id in legacy_rows:
        by_module[module_id].append(audio_asset_id)

    resolved: dict[Any, Any | None] = {}
    for module_id, audio_ids in by_module.items():
        try:
            resolved[module_id] = _resolve_legacy_audio_ids(audio_ids)
        except RuntimeError as exc:
            raise RuntimeError(f"Listening module {module_id}: {exc}") from exc

    for module_id, audio_asset_id in resolved.items():
        if audio_asset_id is not None:
            connection.execute(
                sa.text(
                    "UPDATE test_modules SET audio_asset_id = :audio_asset_id "
                    "WHERE id = :module_id"
                ),
                {"module_id": module_id, "audio_asset_id": audio_asset_id},
            )

    op.drop_constraint(
        "fk_listening_parts_audio_asset_id_assets", "listening_parts", type_="foreignkey"
    )
    op.drop_column("listening_parts", "audio_asset_id")


def downgrade() -> None:
    op.add_column("listening_parts", sa.Column("audio_asset_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_listening_parts_audio_asset_id_assets",
        "listening_parts",
        "assets",
        ["audio_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        "UPDATE listening_parts AS part SET audio_asset_id = module.audio_asset_id "
        "FROM test_modules AS module WHERE part.module_id = module.id"
    )
    op.drop_constraint(
        "fk_test_modules_audio_asset_id_assets", "test_modules", type_="foreignkey"
    )
    op.drop_column("test_modules", "audio_asset_id")
