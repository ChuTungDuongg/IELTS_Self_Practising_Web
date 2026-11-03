"""Optional human interval evaluation, never input to diarization or IELTS inference."""

from typing import Literal

from pydantic import Field

from app.evaluation.speaking.diarization_models import SpeakerTurn
from app.evaluation.speaking.replay_models import read_json
from app.schemas.speaking_grading import StrictDTO


class HumanSpan(SpeakerTurn):
    source: str
    role: Literal["candidate", "examiner"]
    part_number: Literal[1, 2, 3] | None = None


class HumanSegmentation(StrictDTO):
    schema_version: Literal[1] = 1
    truth_source: Literal["human"]
    verified: bool = False
    annotation_complete: bool = False
    provenance: str = Field(min_length=1, max_length=2000)
    source_fingerprints: dict[str, str]
    turns: list[HumanSpan] = Field(max_length=20000)
    responses: list[HumanSpan] = Field(default_factory=list, max_length=1000)


def union(spans):
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def duration(spans):
    return sum(b - a for a, b in union(spans))


def overlap(left, right):
    first, second = union(left), union(right)
    i = j = total = 0
    while i < len(first) and j < len(second):
        a, b = first[i]
        c, d = second[j]
        total += max(0, min(b, d) - max(a, c))
        if b <= d:
            i += 1
        else:
            j += 1
    return total


def boundary_pairs(predicted, reference):
    remaining, errors, pairs = list(reference), [], []
    for interval in predicted:
        matches = [(overlap([interval], [ref]), index) for index, ref in enumerate(remaining)]
        if not matches or max(matches)[0] == 0:
            continue
        _, index = max(matches)
        target = remaining.pop(index)
        pairs.append((interval, target))
        errors.extend([abs(interval[0] - target[0]), abs(interval[1] - target[1])])
    return {
        "matched": len(pairs),
        "predicted_unmatched": len(predicted) - len(pairs),
        "reference_unmatched": len(remaining),
        "boundary_mae_ms": sum(errors) / len(errors) if errors else None,
    }


def evaluate_segmentation(root, results, proposals, state):
    path = root / "segmentation_labels.json"
    if not path.exists():
        return {"status": "HUMAN_SEGMENTATION_UNAVAILABLE", "metrics": None}
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Outside root")
        truth = read_json(path, HumanSegmentation)
    except (ValueError, OSError):
        return {"status": "HUMAN_SEGMENTATION_INVALID", "metrics": None}
    if not truth.verified or not truth.annotation_complete:
        return {"status": "HUMAN_SEGMENTATION_UNVERIFIED_OR_INCOMPLETE", "metrics": None}
    by_source = {r.source: r for r in results}
    if truth.source_fingerprints != {r.source: r.source_sha256 for r in results} or any(
        t.source not in by_source or t.end_ms > by_source[t.source].duration_ms
        for t in [*truth.turns, *truth.responses]
    ):
        return {"status": "HUMAN_SEGMENTATION_SOURCE_MISMATCH", "metrics": None}
    measured = []
    for source, result in by_source.items():
        candidate = [
            (t.start_ms, t.end_ms)
            for t in truth.turns
            if t.source == source and t.role == "candidate"
        ]
        examiner = [
            (t.start_ms, t.end_ms)
            for t in truth.turns
            if t.source == source and t.role == "examiner"
        ]
        selected = [p for p in proposals.segments if p.source == source and p.selected]
        windows = [(p.start_ms, p.end_ms) for p in selected]
        covered, contaminated = overlap(windows, candidate), overlap(windows, examiner)
        total_candidate, total_examiner = duration(candidate), duration(examiner)
        speaker = state.candidate_speakers.get(source)
        predicted_turns = (
            [(t.start_ms, t.end_ms) for t in result.regular if t.speaker_id == speaker]
            if speaker
            else []
        )
        labeled_parts = [
            t for t in truth.turns if t.source == source and t.role == "candidate" and t.part_number
        ]
        assigned_ms = sum(
            overlap([(p.start_ms, p.end_ms)], [(t.start_ms, t.end_ms)])
            for p in selected
            if p.part_number
            for t in labeled_parts
        )
        correct_ms = sum(
            overlap([(p.start_ms, p.end_ms)], [(t.start_ms, t.end_ms)])
            for p in selected
            for t in labeled_parts
            if p.part_number == t.part_number
        )
        reference_responses = [
            t for t in truth.responses if t.source == source and t.role == "candidate"
        ]
        matched_responses = 0
        remaining = list(selected)
        for target in reference_responses:
            options = []
            for index, predicted in enumerate(remaining):
                common = overlap(
                    [(predicted.start_ms, predicted.end_ms)], [(target.start_ms, target.end_ms)]
                )
                denominator = duration(
                    [(predicted.start_ms, predicted.end_ms), (target.start_ms, target.end_ms)]
                )
                if predicted.part_number == target.part_number and target.part_number is not None:
                    options.append((common / denominator, index))
            if options and max(options)[0] >= 0.5:
                _, index = max(options)
                remaining.pop(index)
                matched_responses += 1
        measured.append(
            {
                "source_id": result.cache_key[:12],
                "candidate_reference_ms": total_candidate,
                "candidate_covered_ms": covered,
                "candidate_excluded_ms": total_candidate - covered,
                "candidate_coverage": covered / total_candidate if total_candidate else None,
                "examiner_contamination_ms": contaminated,
                "examiner_contamination_ratio_of_selected_audio": contaminated / duration(windows)
                if duration(windows)
                else None,
                "candidate_attribution_duration_error_ratio": (
                    total_candidate - covered + contaminated
                )
                / (total_candidate + total_examiner)
                if total_candidate + total_examiner
                else None,
                "candidate_turn_boundaries": boundary_pairs(predicted_turns, candidate)
                if speaker
                else None,
                "part_assignment_accuracy_on_assigned_ms": correct_ms / assigned_ms
                if assigned_ms
                else None,
                "response_assignment_accuracy_iou_half": matched_responses
                / len(reference_responses)
                if reference_responses
                else None,
                "reference_response_count": len(reference_responses),
            }
        )
    return {
        "status": "HUMAN_INTERVAL_COMPARISON",
        "metrics": measured,
        "scope": "Private proposed windows; binary candidate attribution, not full multi-speaker DER or IELTS accuracy.",
        "role_verification": proposals.role_verification,
    }
