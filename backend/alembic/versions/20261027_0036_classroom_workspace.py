"""Additive classroom feed, discussions and structured learning content.

Revision ID: 20261027_0036
Revises: 20261013_0035
"""

import sqlalchemy as sa

from alembic import op

revision = "20261027_0036"
down_revision = "20261013_0035"
branch_labels = None
depends_on = None


def identity():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def classroom():
    return sa.Column(
        "classroom_id",
        sa.Uuid(),
        sa.ForeignKey("classrooms.id", ondelete="RESTRICT"),
        nullable=False,
    )


def timestamps():
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def lifecycle():
    return (
        sa.Column("status", sa.String(20), server_default="DRAFT", nullable=False),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="status"),
    )


def upgrade():
    # PostgreSQL labels are additive; do not rewrite existing notification history.
    op.execute(
        "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'CLASSROOM_ANNOUNCEMENT_PUBLISHED'"
    )
    op.execute("ALTER TYPE notification_entity_type ADD VALUE IF NOT EXISTS 'CLASSROOM_POST'")
    op.add_column(
        "classrooms",
        sa.Column("content_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_unique_constraint(
        "uq_classroom_assignments_classroom_id_id", "classroom_assignments", ["classroom_id", "id"]
    )
    op.create_index(
        "ix_classroom_assignments_feed",
        "classroom_assignments",
        ["classroom_id", "status", "created_at", "id"],
    )
    op.create_table(
        "classroom_sections",
        identity(),
        classroom(),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False),
        *lifecycle(),
        *timestamps(),
        sa.UniqueConstraint("classroom_id", "id"),
        sa.CheckConstraint("position >= 0", name="position"),
    )
    op.create_index(
        "ix_classroom_sections_order", "classroom_sections", ["classroom_id", "position", "id"]
    )
    op.create_table(
        "classroom_resources",
        identity(),
        classroom(),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("url", sa.String(2048)),
        sa.Column("storage_key", sa.String(512), unique=True),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("media_type", sa.String(120)),
        sa.Column("size_bytes", sa.Integer()),
        *lifecycle(),
        *timestamps(),
        sa.UniqueConstraint("classroom_id", "id"),
        sa.CheckConstraint("kind IN ('TEXT','LINK','FILE')", name="kind"),
        sa.CheckConstraint(
            "(kind='TEXT' AND body IS NOT NULL AND url IS NULL AND storage_key IS NULL) OR "
            "(kind='LINK' AND url IS NOT NULL AND body IS NULL AND storage_key IS NULL) OR "
            "(kind='FILE' AND storage_key IS NOT NULL AND body IS NULL AND url IS NULL "
            "AND original_filename IS NOT NULL AND media_type IS NOT NULL AND size_bytes > 0)",
            name="target",
        ),
    )
    op.create_index(
        "ix_classroom_resources_visibility", "classroom_resources", ["classroom_id", "status", "id"]
    )
    op.create_table(
        "classroom_content_items",
        identity(),
        classroom(),
        sa.Column("section_id", sa.Uuid()),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("assignment_id", sa.Uuid()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["classroom_id", "section_id"],
            ["classroom_sections.classroom_id", "classroom_sections.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id", "resource_id"],
            ["classroom_resources.classroom_id", "classroom_resources.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id", "assignment_id"],
            ["classroom_assignments.classroom_id", "classroom_assignments.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(resource_id IS NOT NULL)::int + (assignment_id IS NOT NULL)::int = 1",
            name="one_target",
        ),
        sa.CheckConstraint("position >= 0", name="position"),
        sa.UniqueConstraint("resource_id"),
        sa.UniqueConstraint("assignment_id"),
    )
    op.create_index(
        "ix_classroom_content_items_order",
        "classroom_content_items",
        ["classroom_id", "section_id", "position", "id"],
    )
    op.create_table(
        "classroom_posts",
        identity(),
        classroom(),
        sa.Column(
            "author_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(240)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("locked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *lifecycle(),
        *timestamps(),
        sa.CheckConstraint("kind IN ('ANNOUNCEMENT','DISCUSSION')", name="kind"),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 20000", name="body_length"),
    )
    op.create_index("ix_classroom_posts_classroom_id", "classroom_posts", ["classroom_id"])
    op.create_index(
        "ix_classroom_posts_feed",
        "classroom_posts",
        ["classroom_id", "status", "pinned", "created_at", "id"],
    )
    op.create_table(
        "classroom_post_resources",
        sa.Column(
            "post_id",
            sa.Uuid(),
            sa.ForeignKey("classroom_posts.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "resource_id",
            sa.Uuid(),
            sa.ForeignKey("classroom_resources.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_classroom_post_resources_resource_id", "classroom_post_resources", ["resource_id"]
    )
    op.create_table(
        "classroom_comments",
        identity(),
        sa.Column(
            "post_id",
            sa.Uuid(),
            sa.ForeignKey("classroom_posts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "author_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("state", sa.String(20), server_default="VISIBLE", nullable=False),
        *timestamps(),
        sa.CheckConstraint("state IN ('VISIBLE','RETRACTED','MODERATED')", name="state"),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 5000", name="body_length"),
    )
    op.create_index(
        "ix_classroom_comments_thread", "classroom_comments", ["post_id", "created_at", "id"]
    )


def downgrade():
    # Never erase discussion/course history through downgrade.
    connection = op.get_bind()
    for table in (
        "classroom_posts",
        "classroom_comments",
        "classroom_resources",
        "classroom_sections",
        "classroom_content_items",
    ):
        if connection.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Classroom workspace history exists; downgrade refused.")
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM notifications WHERE entity_type::text = 'CLASSROOM_POST')"
        )
    ):
        raise RuntimeError("Classroom announcement notification history exists; downgrade refused.")
    for table in (
        "classroom_comments",
        "classroom_post_resources",
        "classroom_posts",
        "classroom_content_items",
        "classroom_resources",
        "classroom_sections",
    ):
        op.drop_table(table)
    op.drop_index("ix_classroom_assignments_feed", table_name="classroom_assignments")
    op.drop_constraint(
        "uq_classroom_assignments_classroom_id_id", "classroom_assignments", type_="unique"
    )
    op.drop_column("classrooms", "content_revision")
    # As in governance migration 0024, additive PostgreSQL enum labels remain.
