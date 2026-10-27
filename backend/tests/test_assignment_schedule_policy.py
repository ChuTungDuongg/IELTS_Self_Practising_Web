from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.assignment_scheduling import ExtensionWrite, SchedulePolicy
from app.services.assignment_policy import resolve_policy, start_denial, submission_status

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "fields",
    [
        {"due_at": "2026-11-07T12:00:00"},
        {"available_from": NOW, "due_at": NOW},
        {"due_at": NOW, "cutoff_at": NOW - timedelta(seconds=1)},
        {"available_from": NOW, "cutoff_at": NOW},
        {"max_attempts": 0},
        {"due_at": 1700000000},
        {"due_at": "1700000000"},
    ],
)
def test_invalid_policy(fields):
    with pytest.raises(ValidationError):
        SchedulePolicy(**fields)


def test_boundaries_and_late_rules():
    p = SchedulePolicy(
        available_from=NOW,
        due_at=NOW + timedelta(hours=1),
        cutoff_at=NOW + timedelta(hours=2),
        max_attempts=1,
    )
    assert start_denial(p, NOW - timedelta(microseconds=1), 0) == "ASSIGNMENT_SCHEDULED"
    assert start_denial(p, NOW, 0) is None
    assert start_denial(p, p.cutoff_at, 0) is None
    assert start_denial(p, p.cutoff_at + timedelta(microseconds=1), 0) == "ASSIGNMENT_CLOSED"
    assert start_denial(p, NOW, 1) == "ASSIGNMENT_ATTEMPT_LIMIT"
    assert submission_status(p, p.due_at) == "SUBMITTED_ON_TIME"
    assert submission_status(p, p.cutoff_at) == "SUBMITTED_LATE"
    assert submission_status(p, p.cutoff_at + timedelta(microseconds=1)) == "SUBMITTED_NOT_ACCEPTED"
    assert (
        submission_status(p.model_copy(update={"allow_late_submission": False}), p.cutoff_at)
        == "SUBMITTED_NOT_ACCEPTED"
    )


def test_explicit_extension_inherit_remove_and_additional_attempts():
    base = SchedulePolicy(due_at=NOW, cutoff_at=NOW + timedelta(days=1), max_attempts=2)
    extension = ExtensionWrite(
        override_due=True, due_at_override=NOW + timedelta(hours=12), additional_attempts=1
    )
    policy = resolve_policy(base, extension)
    assert policy.due_at == extension.due_at_override and policy.max_attempts == 3
    assert resolve_policy(base, ExtensionWrite(override_due=True)).due_at is None
    assert resolve_policy(SchedulePolicy(), extension).max_attempts is None


def test_offset_timezones_compare_as_instants():
    p = SchedulePolicy(due_at="2026-11-07T19:00:00+07:00")
    assert submission_status(p, NOW) == "SUBMITTED_ON_TIME"
    assert submission_status(p, NOW + timedelta(seconds=1)) == "SUBMITTED_LATE"
