"""Private review/approval tests. All audio/model output here is fictional fixture data."""

import hashlib

import pytest
from test_speaking_diarization import result

from app.core.config import Settings
from app.evaluation.speaking import replay_segment_review as review
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_cache import read_checkpoint, save_checkpoint
from app.evaluation.speaking.replay_models import ReplayManifest


@pytest.fixture
def draft(tmp_path, monkeypatch):
    root = tmp_path / "private"
    root.mkdir()
    source = root / "full_speaking.wav"
    source.write_bytes(b"fictional audio fixture; not real speech")
    item = result(
        [
            ("e", 0, 1000),
            ("c", 2000, 10000),
            ("e", 20000, 21000),
            ("c", 22000, 30000),
            ("e", 40000, 41000),
            ("c", 42000, 90000),
            ("e", 100000, 101000),
            ("c", 102000, 115000),
        ]
    )
    item.source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = {
        "sha256": item.source_sha256,
        "duration_ms": item.duration_ms,
        "format": "wav",
        "size_bytes": source.stat().st_size,
    }
    monkeypatch.setattr(review, "probe_audio", lambda *_: metadata)
    save_checkpoint(
        root / "diarization.json",
        {
            "schema_version": 1,
            "identity": "test-draft",
            "pause_tolerance_ms": 3000,
            "sources": [item.model_dump(mode="json")],
        },
    )
    return root, item, metadata


def questions(root, bundle):
    path = root / "questions.json"
    save_checkpoint(
        path,
        {
            "schema_version": 1,
            "questions": {
                p.id: {"prompt_text": "Fictional human supplied question", "verified": True}
                for p in bundle.segments
                if p.selected
            },
        },
    )
    return path


def ready(root):
    bundle = review.update_review(root, candidate="c", part_boundaries=[20000, 100000])
    return review.update_review(root, questions=questions(root, bundle))


def test_confirmation_does_not_approve_boundaries_parts_or_prompts(draft):
    root, _, _ = draft
    bundle = review.generate_proposals(root)
    assert bundle.role_verification == "pending" and bundle.boundary_verification == "pending"
    assert not (root / "segments.json").exists()
    assert bundle.roles["full_speaking.wav"]["c"]["suggested_role"] == "candidate"
    # Operator corrects a hypothetical wrong heuristic. Identity confirmation alone never grades.
    confirmed = review.update_review(root, candidate="e")
    assert (
        confirmed.role_verification == "confirmed" and confirmed.boundary_verification == "pending"
    )
    assert all(p.speaker_id == "e" and p.part_number is None for p in confirmed.segments)
    with pytest.raises(BenchmarkInputError, match="PART_BOUNDARIES"):
        review.approve_segments(root, Settings(_env_file=None))


def test_parts_and_prompts_must_be_independently_verified(draft):
    root, _, _ = draft
    review.update_review(root, candidate="c", part_boundaries=[20000, 100000])
    with pytest.raises(BenchmarkInputError, match="PROMPT_CONTEXT"):
        review.approve_segments(root, Settings(_env_file=None))
    assert not (root / "segments.json").exists()


def test_final_approval_emits_existing_strict_manifest_and_receipt(draft):
    root, _, metadata = draft
    ready(root)
    manifest = review.approve_segments(root, Settings(_env_file=None))
    assert isinstance(manifest, ReplayManifest) and manifest.candidate_only_verified
    assert not manifest.grading_limitations()
    assert {s.part_number for s in manifest.segments} == {1, 2, 3}
    assert all(s.speaker_id == manifest.candidate_id for s in manifest.segments)
    receipt = read_checkpoint(root / "segments.approval.json")
    assert receipt["candidate_speakers"] == {"full_speaking.wav": "c"}
    review.verify_approval(root, manifest, {"full_speaking.wav": metadata})
    with pytest.raises(BenchmarkInputError, match="APPROVED_SOURCE_CHANGED"):
        review.verify_approval(root, manifest, {"full_speaking.wav": {"sha256": "0" * 64}})
    changed = manifest.model_copy(deep=True)
    changed.segments[0].start_ms += 1
    with pytest.raises(BenchmarkInputError, match="APPROVAL_CHANGED"):
        review.verify_approval(root, changed, {"full_speaking.wav": metadata})


def test_model_draft_updates_never_overwrite_approved_segments(draft):
    root, _, _ = draft
    ready(root)
    review.approve_segments(root, Settings(_env_file=None))
    before = (root / "segments.json").read_bytes()
    review.generate_proposals(root)
    review.update_review(root, candidate="e")
    assert (root / "segments.json").read_bytes() == before


def test_small_boundary_edit_updates_only_proposal_and_known_overlap_blocks_approval(draft):
    from app.evaluation.speaking.diarization_models import SpeakerTurn

    root, item, _ = draft
    item.regular.append(SpeakerTurn(id="overlap", speaker_id="e", start_ms=5000, end_ms=5500))
    data = read_checkpoint(root / "diarization.json")
    data["sources"] = [item.model_dump(mode="json")]
    save_checkpoint(root / "diarization.json", data)
    bundle = ready(root)
    blocked = next(p for p in bundle.segments if "OTHER_SPEAKER_OVERLAP" in p.flags)
    review.update_review(root, acknowledge=[blocked.id])
    with pytest.raises(BenchmarkInputError, match="OVERLAPPING"):
        review.approve_segments(root, Settings(_env_file=None))
    edited = review.update_review(root, edit=(blocked.id, 5600, blocked.end_ms))
    assert (
        "OTHER_SPEAKER_OVERLAP" not in next(p for p in edited.segments if p.id == blocked.id).flags
    )
    assert not (root / "segments.json").exists()
    assert review.approve_segments(root, Settings(_env_file=None)).candidate_only_verified


def test_invalid_edits_and_foreign_question_paths_are_rejected(draft, tmp_path):
    root, _, _ = draft
    bundle = review.update_review(root, candidate="c")
    identifier = bundle.segments[0].id
    with pytest.raises(BenchmarkInputError, match="RANGE_INVALID"):
        review.update_review(root, edit=(identifier, -1, 10))
    with pytest.raises(BenchmarkInputError, match="PRIVATE_ROOT"):
        review.update_review(root, questions=tmp_path / "outside.json")


def test_manual_manifest_without_sidecar_remains_supported(tmp_path):
    from test_speaking_replay_contract import manifest

    review.verify_approval(tmp_path, ReplayManifest.model_validate(manifest()), {})


def test_changed_recording_requires_new_diarization(draft):
    root, _, _ = draft
    (root / "full_speaking.wav").write_bytes(b"another recording")
    with pytest.raises(BenchmarkInputError, match="SOURCE_CHANGED"):
        review.generate_proposals(root)


def test_separate_file_speakers_are_never_implicitly_linked(draft):
    root, item, _ = draft
    others = []
    for part in (1, 2, 3):
        name = f"part{part}.wav"
        (root / name).write_bytes((root / item.source).read_bytes())
        others.append(item.model_copy(update={"source": name}))
    save_checkpoint(
        root / "diarization.json",
        {
            "schema_version": 1,
            "identity": "three-files",
            "pause_tolerance_ms": 3000,
            "sources": [r.model_dump(mode="json") for r in others],
        },
    )
    with pytest.raises(BenchmarkInputError, match="FILE_AMBIGUOUS"):
        review.update_review(root, candidate="c")
    bundle = review.update_review(root, file_parts=True)
    assert bundle.role_verification == "pending"


def test_review_is_local_safe_and_reports_ambiguity(draft):
    root, _, _ = draft
    text = review.review_summary(root)
    assert "pending" in text and "no Azure/OpenAI calls" in text
    assert "Part=None" in text and "prompt_verified=False" in text
    assert str(root) not in text
    html = (root / "review.local.html").read_text()
    assert 'controls preload="none"' in html and "connect-src &#x27;none&#x27;" in html
    assert "https://" not in html and "http://" not in html and "<audio autoplay" not in html
    assert 'data-start="' in html and "other.pause()" in html


def test_new_model_draft_archives_old_operator_review(draft):
    root, _, _ = draft
    ready(root)
    previous = read_checkpoint(root / "segments.review.json")
    raw = read_checkpoint(root / "diarization.json")
    raw["identity"] = "another-model-configuration"
    save_checkpoint(root / "diarization.json", raw)
    generated = review.generate_proposals(root)
    assert generated.role_verification == "pending"
    (archive,) = root.glob("SENSITIVE-review-*.json")
    assert read_checkpoint(archive) == previous
