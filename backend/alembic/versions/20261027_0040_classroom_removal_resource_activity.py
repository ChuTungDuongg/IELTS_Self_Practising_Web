"""Safe classroom removal and canonical resource publication metadata."""

import sqlalchemy as sa

from alembic import op

revision = "20261027_0040"
down_revision = "20261027_0039"
branch_labels = depends_on = None


def upgrade():
    op.add_column("classroom_posts", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("classroom_resources", sa.Column("published_at", sa.DateTime(timezone=True)))
    op.add_column("classroom_resources", sa.Column("created_by_user_id", sa.Uuid()))
    op.create_foreign_key(
        op.f("fk_classroom_resources_created_by_user_id_users"),
        "classroom_resources",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "UPDATE classroom_resources SET published_at = created_at WHERE status = 'PUBLISHED'"
    )
    op.add_column(
        "classroom_assignments",
        sa.Column("classwork_hidden", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM classroom_posts WHERE deleted_at IS NOT NULL) OR EXISTS(SELECT 1 FROM classroom_assignments WHERE classwork_hidden)"
        )
    ):
        raise RuntimeError("Retained deletion or removal state prevents downgrade")
    op.drop_column("classroom_assignments", "classwork_hidden")
    op.drop_constraint(
        op.f("fk_classroom_resources_created_by_user_id_users"),
        "classroom_resources",
        type_="foreignkey",
    )
    op.drop_column("classroom_resources", "created_by_user_id")
    op.drop_column("classroom_resources", "published_at")
    op.drop_column("classroom_posts", "deleted_at")
