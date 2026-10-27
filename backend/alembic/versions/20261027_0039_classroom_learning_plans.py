"""Learning plans and explicit overall planning target; native result tables stay authoritative."""

import sqlalchemy as sa

from alembic import op

revision = "20261027_0039"
down_revision = "20261027_0038"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("target_overall_band", sa.Numeric(3, 1)))
    op.create_check_constraint(
        "ck_users_target_overall_half_band",
        "users",
        "target_overall_band IS NULL OR (target_overall_band BETWEEN 0 AND 9 AND mod(target_overall_band * 2, 1) = 0)",
    )

    def fk(table):
        return sa.ForeignKey(f"{table}.id", ondelete="RESTRICT")

    op.create_table(
        "classroom_learning_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("classroom_id", sa.Uuid(), fk("classrooms"), nullable=False),
        sa.Column("student_id", sa.Uuid(), fk("users"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), fk("users"), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), fk("users"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("target_skill", sa.String(16), nullable=False),
        sa.Column("focus_area", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("classroom_id", "id"),
        sa.CheckConstraint(
            "target_skill IN ('READING','LISTENING','WRITING','SPEAKING')",
            name="ck_classroom_learning_plans_skill",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','COMPLETED','ARCHIVED')", name="ck_classroom_learning_plans_status"
        ),
    )
    op.create_index(
        "ix_classroom_learning_plans_student",
        "classroom_learning_plans",
        ["classroom_id", "student_id", "status", "created_at"],
    )
    op.create_table(
        "classroom_learning_plan_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("classroom_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid()),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by_user_id", sa.Uuid(), fk("users")),
        sa.ForeignKeyConstraint(
            ["classroom_id", "plan_id"],
            ["classroom_learning_plans.classroom_id", "classroom_learning_plans.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id", "assignment_id"],
            ["classroom_assignments.classroom_id", "classroom_assignments.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id", "resource_id"],
            ["classroom_resources.classroom_id", "classroom_resources.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(assignment_id IS NOT NULL)::int + (resource_id IS NOT NULL)::int = 1",
            name="ck_classroom_learning_plan_items_target",
        ),
        sa.CheckConstraint(
            "assignment_id IS NULL OR (completed_at IS NULL AND completed_by_user_id IS NULL)",
            name="ck_classroom_learning_plan_items_resource_completion",
        ),
        sa.UniqueConstraint("plan_id", "assignment_id"),
        sa.UniqueConstraint("plan_id", "resource_id"),
    )
    op.create_index(
        "ix_classroom_learning_plan_items_plan",
        "classroom_learning_plan_items",
        ["plan_id", "active", "position"],
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM classroom_learning_plans) OR EXISTS(SELECT 1 FROM users WHERE target_overall_band IS NOT NULL)"
        )
    ):
        raise RuntimeError("Learning plans and explicit goals must be retained")
    op.drop_table("classroom_learning_plan_items")
    op.drop_table("classroom_learning_plans")
    op.drop_constraint(op.f("ck_users_ck_users_target_overall_half_band"), "users", type_="check")
    op.drop_column("users", "target_overall_band")
