"""Allow authorized assignment deletion to remove its policy history."""

from alembic import op

revision = "20261028_0042"
down_revision = "20261027_0041"
branch_labels = depends_on = None


def upgrade():
    # Policy snapshots still cannot be edited. Deleting the assignment now
    # explicitly deletes all of its assessment and scheduling records.
    op.execute(
        "DROP TRIGGER assignment_policy_events_immutable ON classroom_assignment_policy_events"
    )
    op.execute(
        "CREATE TRIGGER assignment_policy_events_immutable BEFORE UPDATE "
        "ON classroom_assignment_policy_events FOR EACH ROW "
        "EXECUTE FUNCTION reject_assignment_policy_event_mutation()"
    )


def downgrade():
    op.execute(
        "DROP TRIGGER assignment_policy_events_immutable ON classroom_assignment_policy_events"
    )
    op.execute(
        "CREATE TRIGGER assignment_policy_events_immutable BEFORE UPDATE OR DELETE "
        "ON classroom_assignment_policy_events FOR EACH ROW "
        "EXECUTE FUNCTION reject_assignment_policy_event_mutation()"
    )
