from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.attempts import AttemptCreate, TimerRequest


def test_legacy_start_defaults_to_full_module():
    request = AttemptCreate(test_version_id=uuid4(), module="READING", timer={"mode": "COUNT_UP"})
    assert request.scope == "FULL_MODULE"
    assert request.focused_unit is None


@pytest.mark.parametrize("duration", [600, 900, 1200, 1500, 1800, 2100, 2400, 3000, 3600, 4200])
def test_timer_structure_leaves_preset_policy_to_attempt_domain(duration):
    assert TimerRequest(mode="COUNTDOWN", duration_seconds=duration).duration_seconds == duration


@pytest.mark.parametrize(
    "timer",
    [
        {"mode": "COUNTDOWN"},
        {"mode": "COUNTDOWN", "duration_seconds": 0},
        {"mode": "COUNT_UP", "duration_seconds": 1200},
    ],
)
def test_timer_still_rejects_invalid_structure(timer):
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(timer)


def test_focused_unit_is_a_discriminated_request_not_three_nullable_ids():
    unit_id = uuid4()
    request = AttemptCreate(
        test_version_id=uuid4(),
        module="READING",
        scope="FOCUSED_UNIT",
        focused_unit={"kind": "READING_PASSAGE", "id": unit_id},
        timer={"mode": "COUNT_UP"},
    )
    assert request.focused_unit.kind == "READING_PASSAGE"
    assert request.focused_unit.id == unit_id
    with pytest.raises(ValidationError):
        AttemptCreate.model_validate(
            {**request.model_dump(), "focused_unit": {"kind": "OTHER", "id": unit_id}}
        )
