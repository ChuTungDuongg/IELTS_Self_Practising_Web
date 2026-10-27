"""Frozen teacher-directed assignment targets; legacy flexible rows remain null."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261027_0041"
down_revision = "20261027_0040"
branch_labels = depends_on = None


def upgrade():
    op.add_column("classroom_assignments", sa.Column("target", postgresql.JSONB()))
    op.create_check_constraint(
        "target_object",
        "classroom_assignments",
        "target IS NULL OR jsonb_typeof(target) = 'object'",
    )
    op.execute("""CREATE FUNCTION protect_classroom_assignment_target() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.target IS DISTINCT FROM OLD.target THEN
          RAISE EXCEPTION 'Assignment targets are immutable; create a new assignment';
        END IF;
        RETURN NEW;
      END $$""")
    op.execute("""CREATE TRIGGER classroom_assignment_target_immutable BEFORE UPDATE ON classroom_assignments
      FOR EACH ROW EXECUTE FUNCTION protect_classroom_assignment_target()""")


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM classroom_assignments WHERE target IS NOT NULL)")
    ):
        raise RuntimeError("Retained teacher assignment targets prevent downgrade")
    op.execute("DROP TRIGGER classroom_assignment_target_immutable ON classroom_assignments")
    op.execute("DROP FUNCTION protect_classroom_assignment_target()")
    op.drop_constraint(
        op.f("ck_classroom_assignments_target_object"), "classroom_assignments", type_="check"
    )
    op.drop_column("classroom_assignments", "target")
