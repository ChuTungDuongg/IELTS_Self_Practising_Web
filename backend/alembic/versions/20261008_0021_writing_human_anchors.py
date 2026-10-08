"""Private versioned human Writing anchors; no production seed data.

Revision ID: 20261008_0021
Revises: 20261008_0020
"""

import sqlalchemy as sa

from alembic import op

revision = "20261008_0021"
down_revision = "20261008_0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "writing_anchor_sets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('DRAFT','ACTIVE','RETIRED')", name="valid_status"),
        sa.CheckConstraint("version > 0", name="positive_version"),
    )
    op.create_index(
        "uq_writing_anchor_sets_version", "writing_anchor_sets", ["version"], unique=True
    )
    for status in ("active", "draft"):
        op.create_index(
            f"uq_writing_anchor_sets_{status}",
            "writing_anchor_sets",
            ["status"],
            unique=True,
            postgresql_where=sa.text(f"status = '{status.upper()}'"),
        )
    op.create_table(
        "writing_human_anchors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "anchor_set_id",
            sa.Uuid(),
            sa.ForeignKey("writing_anchor_sets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "writing_task_id",
            sa.Uuid(),
            sa.ForeignKey("writing_tasks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("response_text", sa.Text(), nullable=False),
        *(
            sa.Column(f"{trait}_score", sa.Numeric(2, 1), nullable=False)
            for trait in ("ta", "cc", "lr", "gra")
        ),
        sa.Column(
            "created_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("admin_note", sa.Text()),
        sa.Column("provenance", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        *(
            sa.CheckConstraint(
                f"{trait}_score >= 0 AND {trait}_score <= 9 AND mod({trait}_score * 2, 1) = 0",
                name=f"{trait}_half_band",
            )
            for trait in ("ta", "cc", "lr", "gra")
        ),
        sa.CheckConstraint("length(btrim(response_text)) > 0", name="nonblank_response"),
    )
    op.create_index(
        "ix_writing_human_anchors_set_task",
        "writing_human_anchors",
        ["anchor_set_id", "writing_task_id"],
    )
    op.execute("""
        CREATE FUNCTION enforce_writing_anchor_immutability() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_status text;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            SELECT status INTO parent_status FROM writing_anchor_sets WHERE id=OLD.anchor_set_id FOR UPDATE;
            IF parent_status <> 'DRAFT' THEN RAISE EXCEPTION 'Frozen anchor content is immutable' USING ERRCODE='23514'; END IF;
          END IF;
          IF TG_OP <> 'DELETE' THEN
            SELECT status INTO parent_status FROM writing_anchor_sets WHERE id=NEW.anchor_set_id FOR UPDATE;
            IF parent_status <> 'DRAFT' THEN RAISE EXCEPTION 'Frozen anchor content is immutable' USING ERRCODE='23514'; END IF;
            RETURN NEW;
          END IF;
          RETURN OLD;
        END $$
    """)
    op.execute(
        "CREATE TRIGGER writing_anchor_content_immutable BEFORE INSERT OR UPDATE OR DELETE ON writing_human_anchors FOR EACH ROW EXECUTE FUNCTION enforce_writing_anchor_immutability()"
    )
    op.execute("""
        CREATE FUNCTION enforce_writing_anchor_set_immutability() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.status <> 'DRAFT' THEN
            IF TG_OP='UPDATE' AND OLD.status='ACTIVE' AND NEW.status='RETIRED' AND NEW.retired_at IS NOT NULL
               AND (to_jsonb(NEW)-ARRAY['status','retired_at','updated_at']) = (to_jsonb(OLD)-ARRAY['status','retired_at','updated_at']) THEN
              RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Frozen anchor set is immutable' USING ERRCODE='23514';
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END $$
    """)
    op.execute(
        "CREATE TRIGGER writing_anchor_set_immutable BEFORE UPDATE OR DELETE ON writing_anchor_sets FOR EACH ROW EXECUTE FUNCTION enforce_writing_anchor_set_immutability()"
    )


def downgrade():
    op.drop_table("writing_human_anchors")
    op.drop_table("writing_anchor_sets")
    op.execute("DROP FUNCTION enforce_writing_anchor_immutability()")
    op.execute("DROP FUNCTION enforce_writing_anchor_set_immutability()")
