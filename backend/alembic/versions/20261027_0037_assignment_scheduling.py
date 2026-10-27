"""Assignment scheduling, individual extensions and auditable policy timeline.

Revision ID: 20261027_0037
Revises: 20261027_0036
"""

import sqlalchemy as sa

from alembic import op

revision = "20261027_0037"
down_revision = "20261027_0036"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("attempts", "test_sessions"):
        op.create_index(
            f"ix_{table}_assignment_progress",
            table,
            ["classroom_assignment_id", "user_id", "started_at", "id"],
            postgresql_where=sa.text("classroom_assignment_id IS NOT NULL"),
        )
    for name in ("available_from", "due_at", "cutoff_at"):
        op.add_column("classroom_assignments", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column("classroom_assignments", sa.Column("max_attempts", sa.Integer()))
    op.add_column(
        "classroom_assignments",
        sa.Column("allow_late_submission", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "classroom_assignments",
        sa.Column("policy_revision", sa.Integer(), server_default="0", nullable=False),
    )
    for name, expression in (
        ("max_attempts", "max_attempts IS NULL OR max_attempts >= 1"),
        ("availability_due", "available_from IS NULL OR due_at IS NULL OR available_from < due_at"),
        ("due_cutoff", "due_at IS NULL OR cutoff_at IS NULL OR due_at <= cutoff_at"),
        (
            "availability_cutoff",
            "available_from IS NULL OR cutoff_at IS NULL OR available_from < cutoff_at",
        ),
    ):
        op.create_check_constraint(
            op.f(f"ck_classroom_assignments_{name}"), "classroom_assignments", expression
        )
    op.create_table(
        "classroom_assignment_extensions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Uuid(),
            sa.ForeignKey("classroom_assignments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "student_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("override_due", sa.Boolean(), nullable=False),
        sa.Column("due_at_override", sa.DateTime(timezone=True)),
        sa.Column("override_cutoff", sa.Boolean(), nullable=False),
        sa.Column("cutoff_at_override", sa.DateTime(timezone=True)),
        sa.Column("additional_attempts", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("assignment_id", "student_id"),
        sa.CheckConstraint("additional_attempts >= 0", name="additional_attempts"),
    )
    op.create_table(
        "classroom_assignment_policy_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Uuid(),
            sa.ForeignKey("classroom_assignments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "effective_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text()),
        *(
            sa.Column(name, sa.DateTime(timezone=True))
            for name in ("available_from", "due_at", "cutoff_at")
        ),
        sa.Column("max_attempts", sa.Integer()),
        sa.Column("allow_late_submission", sa.Boolean(), nullable=False),
        sa.Column("override_due", sa.Boolean(), nullable=False),
        sa.Column("override_cutoff", sa.Boolean(), nullable=False),
        sa.Column("additional_attempts", sa.Integer(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("assignment_id", "revision"),
    )
    op.create_index(
        "ix_assignment_policy_history",
        "classroom_assignment_policy_events",
        ["assignment_id", "student_id", "effective_at", "revision"],
    )
    # History is append-only even for application SQL, and cannot be mutated through ORM.
    op.execute(
        """CREATE FUNCTION reject_assignment_policy_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Assignment policy history is immutable'; END $$"""
    )
    op.execute(
        "CREATE TRIGGER assignment_policy_events_immutable BEFORE UPDATE OR DELETE ON classroom_assignment_policy_events FOR EACH ROW EXECUTE FUNCTION reject_assignment_policy_event_mutation()"
    )
    for label in (
        "ASSIGNMENT_CREATED",
        "ASSIGNMENT_SCHEDULE_CHANGED",
        "ASSIGNMENT_DUE_SOON",
        "ASSIGNMENT_OVERDUE",
        "ASSIGNMENT_EXTENSION_GRANTED",
    ):
        op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{label}'")
    op.execute("ALTER TYPE notification_entity_type ADD VALUE IF NOT EXISTS 'CLASSROOM_ASSIGNMENT'")


def downgrade():
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM classroom_assignment_policy_events) OR EXISTS (SELECT 1 FROM classroom_assignment_extensions) OR EXISTS (SELECT 1 FROM classroom_assignments WHERE available_from IS NOT NULL OR due_at IS NOT NULL OR cutoff_at IS NOT NULL OR max_attempts IS NOT NULL OR NOT allow_late_submission)"
        )
    ):
        raise RuntimeError("Assignment scheduling history exists; downgrade refused")
    op.drop_table("classroom_assignment_policy_events")
    op.execute("DROP FUNCTION reject_assignment_policy_event_mutation()")
    op.drop_table("classroom_assignment_extensions")
    for table in ("attempts", "test_sessions"):
        op.drop_index(f"ix_{table}_assignment_progress", table_name=table)
    for name in ("max_attempts", "availability_due", "due_cutoff", "availability_cutoff"):
        op.drop_constraint(
            op.f(f"ck_classroom_assignments_{name}"), "classroom_assignments", type_="check"
        )
    for name in (
        "available_from",
        "due_at",
        "cutoff_at",
        "max_attempts",
        "allow_late_submission",
        "policy_revision",
    ):
        op.drop_column("classroom_assignments", name)
