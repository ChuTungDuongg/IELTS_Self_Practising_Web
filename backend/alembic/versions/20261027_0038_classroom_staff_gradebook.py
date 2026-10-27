"""Classroom staff invitations and Gradebook policy. Additive; retains exam history."""

import sqlalchemy as sa

from alembic import op

revision = "20261027_0038"
down_revision = "20261027_0037"
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'HUMAN_FINAL_GRADED'")

    def fk(table):
        return sa.ForeignKey(f"{table}.id", ondelete="RESTRICT")

    flags = ("content_manage", "discussion_moderate", "analytics_view", "learning_plans_manage")
    op.create_table(
        "classroom_staff",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("classroom_id", sa.Uuid(), fk("classrooms"), nullable=False),
        sa.Column("user_id", sa.Uuid(), fk("users"), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), fk("users"), nullable=False),
        sa.Column("staff_role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        *[sa.Column(flag, sa.Boolean(), server_default="false", nullable=False) for flag in flags],
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "staff_role IN ('CO_TEACHER','TEACHING_ASSISTANT')", name="ck_classroom_staff_role"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','ACCEPTED','DECLINED','CANCELLED','REVOKED')",
            name="ck_classroom_staff_status",
        ),
    )
    for field in ("classroom_id", "user_id"):
        op.create_index(f"ix_classroom_staff_{field}", "classroom_staff", [field])
    op.create_index(
        "uq_classroom_staff_current",
        "classroom_staff",
        ["classroom_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING','ACCEPTED')"),
    )
    op.create_table(
        "classroom_staff_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("staff_id", sa.Uuid(), fk("classroom_staff"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), fk("users"), nullable=False),
        sa.Column("staff_role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        *[sa.Column(flag, sa.Boolean(), nullable=False) for flag in flags],
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_classroom_staff_events_staff_id", "classroom_staff_events", ["staff_id"])
    op.execute("""CREATE FUNCTION protect_classroom_staff_events() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Staff history is append-only'; END $$""")
    op.execute("""CREATE TRIGGER classroom_staff_events_immutable BEFORE UPDATE OR DELETE ON classroom_staff_events
        FOR EACH ROW EXECUTE FUNCTION protect_classroom_staff_events()""")
    op.add_column(
        "classroom_assignments",
        sa.Column(
            "grade_selection", sa.String(24), nullable=False, server_default="LATEST_ACCEPTED"
        ),
    )
    op.create_check_constraint(
        "ck_classroom_assignments_grade_selection",
        "classroom_assignments",
        "grade_selection IN ('LATEST_ACCEPTED','FIRST_ACCEPTED','BEST_ACCEPTED')",
    )


def downgrade():
    conn = op.get_bind()
    if conn.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM classroom_staff) OR EXISTS(SELECT 1 FROM classroom_assignments WHERE grade_selection <> 'LATEST_ACCEPTED')"
        )
    ):
        raise RuntimeError("Retained staff or Gradebook policies prevent downgrade")
    op.drop_constraint(
        op.f("ck_classroom_assignments_ck_classroom_assignments_grade_selection"),
        "classroom_assignments",
        type_="check",
    )
    op.drop_column("classroom_assignments", "grade_selection")
    op.drop_table("classroom_staff_events")
    op.execute("DROP FUNCTION protect_classroom_staff_events()")
    op.drop_table("classroom_staff")
