"""Interval arithmetic on fictional human annotations, not measured model accuracy."""

from test_speaking_segment_review import draft  # noqa: F401

from app.evaluation.speaking.diarization_evaluation import (
    boundary_pairs,
    evaluate_segmentation,
    overlap,
)
from app.evaluation.speaking.replay_cache import save_checkpoint
from app.evaluation.speaking.replay_segment_review import (
    generate_proposals,
    load_diarization,
    load_state,
    update_review,
)


def test_no_quality_metrics_without_complete_verified_human_truth(draft):  # noqa: F811
    root, _, _ = draft
    data, results = load_diarization(root)
    bundle = generate_proposals(root)
    report = evaluate_segmentation(root, results, bundle, load_state(root, data["identity"]))
    assert report["status"] == "HUMAN_SEGMENTATION_UNAVAILABLE" and report["metrics"] is None


def test_reference_intervals_measure_contamination_and_exclusion(draft):  # noqa: F811
    root, item, _ = draft
    bundle = update_review(root, candidate="c", part_boundaries=[20000, 100000])
    data, results = load_diarization(root)
    turns = [
        {
            **t.model_dump(),
            "source": item.source,
            "role": "candidate" if t.speaker_id == "c" else "examiner",
            "part_number": 1 if t.start_ms < 20000 else 2 if t.start_ms < 100000 else 3,
        }
        for t in item.regular
    ]
    save_checkpoint(
        root / "segmentation_labels.json",
        {
            "schema_version": 1,
            "truth_source": "human",
            "verified": True,
            "annotation_complete": True,
            "provenance": "Fictional interval fixture",
            "source_fingerprints": {item.source: item.source_sha256},
            "turns": turns,
        },
    )
    measured = evaluate_segmentation(root, results, bundle, load_state(root, data["identity"]))
    assert measured["metrics"][0]["candidate_coverage"] == 1
    assert measured["metrics"][0]["examiner_contamination_ms"] == 0
    assert measured["metrics"][0]["candidate_turn_boundaries"]["boundary_mae_ms"] == 0
    assert measured["metrics"][0]["part_assignment_accuracy_on_assigned_ms"] == 1


def test_interval_arithmetic_does_not_double_count_overlap():
    assert overlap([(0, 10), (5, 15)], [(7, 20)]) == 8
    assert boundary_pairs([(0, 10)], [(2, 12), (20, 30)]) == {
        "matched": 1,
        "predicted_unmatched": 0,
        "reference_unmatched": 1,
        "boundary_mae_ms": 2,
    }
