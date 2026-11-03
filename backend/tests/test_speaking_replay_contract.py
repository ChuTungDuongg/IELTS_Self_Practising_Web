"""Replay is separate from labelled benchmark validation and never guesses speakers."""

from pathlib import Path

import pytest
from pydantic import ValidationError


def manifest():
    return {
        "schema_version": 1,
        "source": "full_speaking.wav",
        "candidate_only_verified": True,
        "segments": [
            {
                "id": f"p{part}",
                "part_number": part,
                "start_ms": start,
                "end_ms": start + 2000,
                "prompt_type": "LONG_TURN" if part == 2 else "SHORT_ANSWER",
                "prompt_text": f"Describe fictional topic {part}.",
                "speaker_role": "candidate",
            }
            for part, start in [(1, 0), (2, 3000), (3, 6000)]
        ],
    }


def test_replay_needs_no_human_labels_and_keeps_benchmark_strict():
    from app.evaluation.speaking.models import BenchmarkSample
    from app.evaluation.speaking.replay_models import ReplayManifest

    value = ReplayManifest.model_validate(manifest())
    assert value.candidate_only_verified
    with pytest.raises(ValidationError):
        BenchmarkSample.model_validate({"schema_version": 1, "id": "unlabelled", "responses": []})


@pytest.mark.parametrize(
    "change",
    [
        {"start_ms": -1},
        {"end_ms": 0},
        {"start_ms": 3.5},
        {"source": "../outside.wav"},
        {"source": "https://example.invalid/audio.mp3"},
        {"source": "C:\\private\\audio.wav"},
        {"speaker_id": "another-candidate"},
    ],
)
def test_invalid_segment_metadata_is_rejected(change):
    from app.evaluation.speaking.replay_models import ReplayManifest

    value = manifest()
    value["segments"][0].update(change)
    with pytest.raises(ValidationError):
        ReplayManifest.model_validate(value)


def test_overlap_is_rejected_but_windows_in_different_part_files_are_independent():
    from app.evaluation.speaking.replay_models import ReplayManifest

    value = manifest()
    value["segments"][1]["start_ms"] = 1000
    with pytest.raises(ValidationError):
        ReplayManifest.model_validate(value)
    value["segments"][1]["source"] = "part2.wav"
    assert ReplayManifest.model_validate(value)


def test_part_files_with_examiner_are_not_implicitly_candidate_only():
    from app.evaluation.speaking.replay_models import ReplayManifest

    value = manifest()
    value["candidate_only_verified"] = False
    parsed = ReplayManifest.model_validate(value)
    assert "SPEAKER_NOT_VERIFIED" in parsed.grading_limitations()
    value["candidate_only_verified"] = True
    value["segments"][0]["prompt_text"] = ""
    assert "PROMPT_CONTEXT_REQUIRED" in ReplayManifest.model_validate(value).grading_limitations()


def test_overall_only_truth_does_not_invent_criterion_labels():
    from app.evaluation.speaking.replay_models import ReplayHumanLabels

    labels = ReplayHumanLabels.model_validate(
        {
            "schema_version": 1,
            "bands": {"overall": 6.5},
            "provenance": {
                "kind": "published_human_assessment",
                "reference": "Fictional source",
                "verified": True,
            },
        }
    )
    assert labels.bands.fc is None and labels.bands.overall == 6.5
    invalid = labels.model_dump()
    invalid["provenance"]["kind"] = "ai_prediction"
    with pytest.raises(ValidationError):
        ReplayHumanLabels.model_validate(invalid)


def test_source_cannot_escape_private_root_even_through_symlinks(tmp_path):
    from app.evaluation.speaking.replay_audio import resolve_source

    root = tmp_path / "private"
    root.mkdir()
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"private outside file")
    with pytest.raises(ValueError):
        resolve_source(root, "../outside.wav")
    try:
        (root / "escape.wav").symlink_to(outside)
    except OSError:
        pytest.skip("Host does not permit symlink creation")
    with pytest.raises(ValueError):
        resolve_source(root, "escape.wav")


def test_sensitive_fixture_directories_are_ignored():
    import subprocess

    root = Path(__file__).resolve().parents[2]
    paths = [
        "benchmarks/speaking/private/replay/full_speaking.mp3",
        "benchmarks/speaking/reports/replay/synthetic/summary.json",
    ]
    result = subprocess.run(
        ["git", "check-ignore", *paths], cwd=root, capture_output=True, text=True
    )
    assert result.returncode == 0 and all(path in result.stdout for path in paths)
