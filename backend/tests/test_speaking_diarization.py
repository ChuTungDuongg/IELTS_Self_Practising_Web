"""Deterministic timeline/role tests; no real model, invented quality metric or provider call."""

import pytest
from pydantic import ValidationError

from app.evaluation.speaking.diarization_models import DiarizationResult, SpeakerTurn
from app.evaluation.speaking.replay_segmentation import propose_responses, suggest_roles


def result(turns, *, regular=None, source="full_speaking.wav"):
    parsed = [
        SpeakerTurn(id=f"t{i}", speaker_id=s, start_ms=a, end_ms=b)
        for i, (s, a, b) in enumerate(turns)
    ]
    return DiarizationResult(
        source=source,
        source_sha256="a" * 64,
        duration_ms=180000,
        cache_key="b" * 64,
        identity={"model": "fictional-model", "revision": "test"},
        regular=regular if regular is not None else parsed,
        exclusive=parsed,
    )


def test_speaker_zero_can_be_candidate_but_remains_a_suggestion():
    item = result(
        [
            ("speaker_01", 0, 1000),
            ("speaker_00", 1100, 11000),
            ("speaker_01", 12000, 13000),
            ("speaker_00", 13100, 26000),
        ]
    )
    roles = suggest_roles(item)
    assert roles["speaker_00"]["suggested_role"] == "candidate"
    assert roles["speaker_00"]["verification"] == "pending"
    assert "probability" not in roles["speaker_00"]


def test_ambiguous_roles_and_more_than_two_speakers_are_unknown():
    for turns in (
        [("a", 0, 1000), ("b", 1100, 2100)],
        [("a", 0, 1000), ("b", 1100, 3000), ("c", 3100, 9000)],
        [],
    ):
        assert all(v["suggested_role"] == "unknown" for v in suggest_roles(result(turns)).values())


def test_pauses_are_preserved_but_examiner_interjections_prevent_merging():
    item = result(
        [
            ("e", 0, 1000),
            ("c", 1200, 7000),
            ("c", 9000, 17000),
            ("e", 18000, 18200),
            ("c", 18400, 19000),
        ]
    )
    proposals = propose_responses(item, candidate_speaker="c", pause_tolerance_ms=3000)
    assert len(proposals) == 2
    assert proposals[0].start_ms <= 1200 and proposals[0].end_ms >= 17000
    assert proposals[0].end_ms <= 18000 and proposals[1].start_ms >= 18200
    assert proposals[0].part_number is None and proposals[0].prompt_text == ""


def test_long_turn_alone_does_not_establish_part_two():
    item = result([("e", 0, 1000), ("c", 2000, 125000)])
    (proposal,) = propose_responses(item, candidate_speaker="c")
    assert proposal.part_number is None and not proposal.part_verified


def test_confirmed_part_two_keeps_long_internal_silence_without_concatenation():
    item = result([("e", 0, 1000), ("c", 2000, 7000), ("c", 30000, 100000)])
    proposed = propose_responses(item, candidate_speaker="c")
    assert len(proposed) == 2
    (long_turn,) = propose_responses(item, candidate_speaker="c", boundaries=[1500, 120000])
    assert long_turn.start_ms <= 2000 and long_turn.end_ms >= 100000
    assert long_turn.part_number == 2 and "LONG_SILENCE_REVIEW" in long_turn.flags


def test_silence_or_no_speaker_result_never_invents_candidate_windows():
    assert suggest_roles(result([])) == {}
    assert propose_responses(result([])) == []


def test_overlap_is_retained_and_blocks_approval_not_hidden_by_exclusive_timeline():
    regular = [
        SpeakerTurn(id="a", speaker_id="c", start_ms=1000, end_ms=10000),
        SpeakerTurn(id="b", speaker_id="e", start_ms=5000, end_ms=5500),
    ]
    item = result([("c", 1000, 10000)], regular=regular)
    (proposal,) = propose_responses(item, candidate_speaker="c")
    assert "OTHER_SPEAKER_OVERLAP" in proposal.flags


@pytest.mark.parametrize("bounds", [(-1, 10), (10, 10), (20, 10), (0.5, 10)])
def test_turn_bounds_are_strict(bounds):
    with pytest.raises(ValidationError):
        SpeakerTurn(id="t1", speaker_id="a", start_ms=bounds[0], end_ms=bounds[1])
