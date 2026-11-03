"""Conservative conversational proposals, without ASR, role probabilities or invented Parts."""

from statistics import median

from app.evaluation.speaking.diarization_models import ResponseProposal
from app.services.speaking_audio import fingerprint


def suggest_roles(result):
    speakers = sorted({turn.speaker_id for turn in result.regular})
    durations = {
        speaker: [t.end_ms - t.start_ms for t in result.exclusive if t.speaker_id == speaker]
        for speaker in speakers
    }
    roles = {
        speaker: {
            "suggested_role": "unknown",
            "verification": "pending",
            "exclusive_speech_ms": sum(durations[speaker]),
            "evidence": [],
        }
        for speaker in speakers
    }
    if len(speakers) != 2 or any(not durations[s] for s in speakers):
        return roles
    candidate, other = sorted(speakers, key=lambda s: sum(durations[s]), reverse=True)
    turns = sorted(result.exclusive, key=lambda t: t.start_ms)
    patterns = sum(
        a.speaker_id == other
        and b.speaker_id == candidate
        and a.end_ms - a.start_ms <= 5000
        and b.end_ms - b.start_ms >= 1000
        for a, b in zip(turns, turns[1:], strict=False)
    )
    if (
        sum(durations[candidate]) >= 1.5 * sum(durations[other])
        and median(durations[candidate]) >= 1.25 * median(durations[other])
        and patterns >= 2
    ):
        roles[candidate].update(
            suggested_role="candidate",
            evidence=["MORE_SPEECH_SUPPORT_ONLY", "SHORT_TO_LONG_TURN_PATTERNS"],
        )
        roles[other].update(suggested_role="examiner", evidence=["CONVERSATIONAL_COMPLEMENT_ONLY"])
    return roles


def part_at(time, boundaries):
    if boundaries is None:
        return None
    return 1 if time < boundaries[0] else 2 if time < boundaries[1] else 3


def other_overlap(result, speaker, start, end):
    return any(
        t.speaker_id != speaker and t.start_ms < end and t.end_ms > start for t in result.regular
    )


def propose_responses(
    result,
    *,
    candidate_speaker=None,
    boundaries=None,
    file_part=None,
    pause_tolerance_ms=3000,
    padding_ms=150,
):
    if not 0 <= pause_tolerance_ms <= 30000 or not 0 <= padding_ms <= 500:
        raise ValueError("Invalid segmentation configuration")
    roles = suggest_roles(result)
    turns = sorted(result.exclusive, key=lambda t: t.start_ms)
    groups = []
    for turn in turns:
        if candidate_speaker and turn.speaker_id != candidate_speaker:
            continue
        previous = groups[-1][-1] if groups else None
        gap = turn.start_ms - previous.end_ms if previous else None
        same = previous and previous.speaker_id == turn.speaker_id
        part = file_part or part_at(turn.start_ms, boundaries)
        same_part = previous and part == (file_part or part_at(previous.start_ms, boundaries))
        interrupted = previous and other_overlap(
            result, turn.speaker_id, previous.end_ms, turn.start_ms
        )
        if same and same_part and not interrupted and (gap <= pause_tolerance_ms or part == 2):
            groups[-1].append(turn)
        else:
            groups.append([turn])
    proposals = []
    for group in groups:
        first, last = group[0], group[-1]
        others = [t for t in result.regular if t.speaker_id != first.speaker_id]
        start = max(
            0,
            first.start_ms - padding_ms,
            max((t.end_ms for t in others if t.end_ms <= first.start_ms), default=0),
        )
        end = min(
            result.duration_ms,
            last.end_ms + padding_ms,
            min(
                (t.start_ms for t in others if t.start_ms >= last.end_ms),
                default=result.duration_ms,
            ),
        )
        flags = ["BOUNDARIES_NEED_OPERATOR_REVIEW"]
        if other_overlap(result, first.speaker_id, start, end):
            flags.append("OTHER_SPEAKER_OVERLAP")
        if last.end_ms - first.start_ms < 1000:
            flags.append("SHORT_ANSWER_OR_INTERJECTION")
        if any(
            b.start_ms - a.end_ms > pause_tolerance_ms
            for a, b in zip(group, group[1:], strict=False)
        ):
            flags.append("LONG_SILENCE_REVIEW")
        part = file_part or part_at(first.start_ms, boundaries)
        if boundaries and any(start < boundary < end for boundary in boundaries):
            part = None
            flags.append("PART_BOUNDARY_INSIDE_RESPONSE")
        prior = [
            t for t in turns if t.speaker_id != first.speaker_id and t.end_ms <= first.start_ms
        ]
        role = "candidate" if candidate_speaker else roles[first.speaker_id]["suggested_role"]
        proposals.append(
            ResponseProposal(
                id="s-"
                + fingerprint(
                    [result.source, result.source_sha256, first.speaker_id, [t.id for t in group]]
                )[:16],
                source=result.source,
                speaker_id=first.speaker_id,
                start_ms=start,
                end_ms=end,
                suggested_role=role,
                selected=role == "candidate",
                turn_ids=[t.id for t in group],
                context_turn_ids=[prior[-1].id] if prior else [],
                part_number=part,
                part_verified=part is not None,
                flags=flags,
            )
        )
    return proposals
