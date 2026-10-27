"""Pure classroom rules, independent of IELTS timers, scores and finalization."""

from app.schemas.assignment_scheduling import ExtensionWrite, SchedulePolicy


def resolve_policy(base: SchedulePolicy, extension: ExtensionWrite | None = None) -> SchedulePolicy:
    if extension is None or getattr(extension, "revoked", False):
        return base
    values = base.model_dump()
    if extension.override_due:
        values["due_at"] = extension.due_at_override
    if extension.override_cutoff:
        values["cutoff_at"] = extension.cutoff_at_override
    resolved = SchedulePolicy.model_validate(values)
    # Base limits are bounded independently; a valid extra allowance may exceed
    # that input bound without changing date validation or unlimited semantics.
    return resolved.model_copy(
        update={
            "max_attempts": base.max_attempts + extension.additional_attempts
            if base.max_attempts is not None
            else None
        }
    )


def start_denial(policy: SchedulePolicy, now, used: int) -> str | None:
    if policy.available_from and now < policy.available_from:
        return "ASSIGNMENT_SCHEDULED"
    if policy.cutoff_at and now > policy.cutoff_at:
        return "ASSIGNMENT_CLOSED"
    if not policy.allow_late_submission and policy.due_at and now > policy.due_at:
        return "ASSIGNMENT_LATE_DISABLED"
    if policy.max_attempts is not None and used >= policy.max_attempts:
        return "ASSIGNMENT_ATTEMPT_LIMIT"
    return None


def submission_status(policy: SchedulePolicy, completed_at) -> str:
    if policy.cutoff_at and completed_at > policy.cutoff_at:
        return "SUBMITTED_NOT_ACCEPTED"
    if policy.due_at and completed_at > policy.due_at:
        return "SUBMITTED_LATE" if policy.allow_late_submission else "SUBMITTED_NOT_ACCEPTED"
    return "SUBMITTED_ON_TIME"
