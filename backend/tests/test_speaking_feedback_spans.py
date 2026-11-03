from uuid import uuid4

import pytest
from test_speaking_ai import evidence, feature_bundle

from app.schemas.speaking_grading import CriterionFeedbackInput
from app.services.speaking_feedback import resolve_feedback


def sample():
    bundle = feature_bundle()
    bundle["profile"] = "speaking_hybrid_v1"
    result = evidence(features=bundle)
    row = result.responses[0]
    from app.schemas.speaking_ai import FluencyEvent
    from app.schemas.speaking_timeline import AudioSegmentMapping

    row.features.timeline = [
        AudioSegmentMapping(
            response_id=row.response_id,
            take_number=1,
            segment_id=uuid4(),
            normalized_start_ms=0,
            normalized_end_ms=10000,
        )
    ]
    row.features.fluency.events = [
        FluencyEvent(evidence_id="fc_pause_1", kind="pause", start_ms=2000, end_ms=2500)
    ]
    return result


def feedback(ids, **changes):
    return CriterionFeedbackInput(
        feedback="Overview",
        strengths=[],
        improvements=[],
        local_comments=[
            dict(text="A pause is audible here.", evidence_ids=ids, scope="LOCAL", **changes)
        ],
    )


def test_server_resolves_span_and_does_not_accept_model_timestamps():
    source = sample()
    result = resolve_feedback("fc", source, feedback(["fc_pause_1"]))
    span = result.local_comments[0].audio_span
    assert span.start_ms == 2000 and span.end_ms == 2500
    assert span.response_id == source.responses[0].response_id
    with pytest.raises(ValueError):
        feedback(["fc_pause_1"], audio_span={"start_ms": 0})


@pytest.mark.parametrize("ids", [["invented"], [], ["fc_pause_1", "invented"]])
def test_unknown_ids_never_create_localized_claims(ids):
    with pytest.raises(ValueError):
        resolve_feedback("fc", sample(), feedback(ids))


def test_cross_criterion_ids_rejected_and_overview_has_no_timestamp():
    with pytest.raises(ValueError):
        resolve_feedback("pr", sample(), feedback(["fc_pause_1"]))
    item = CriterionFeedbackInput(
        feedback="Overview",
        strengths=[],
        improvements=[],
        local_comments=[dict(text="Overall organization.", evidence_ids=[], scope="OVERVIEW")],
    )
    assert resolve_feedback("fc", sample(), item).local_comments[0].audio_span is None
