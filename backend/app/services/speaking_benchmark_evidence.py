"""Project approved provider evidence through the production feature/scorer contracts."""

from uuid import NAMESPACE_URL, uuid5

from app.services.speaking_audio import fingerprint
from app.services.speaking_features import build_feature_bundle
from app.services.speaking_hybrid import analysis_to_asr
from app.services.speaking_scorer import build_attempt_evidence


async def response_evidence(audio, segment, speech, lexical, settings):
    transcript = analysis_to_asr(
        lexical if lexical is not None else speech, audio, independent=lexical is not None
    )
    features = await build_feature_bundle(
        audio,
        transcript,
        settings,
        part_number=segment.part_number,
        speech_analysis=speech,
        lexical_analysis=lexical,
    )
    return {
        "response_id": audio.timeline[0].response_id,
        "prompt_id": uuid5(NAMESPACE_URL, fingerprint([segment.prompt_text, segment.cue_points])),
        "part_number": segment.part_number,
        "prompt_type": segment.prompt_type,
        "prompt_text": segment.prompt_text,
        "cue_points": segment.cue_points,
        "verbatim": transcript.text,
        "clean": " ".join(transcript.text.split()),
        "words": transcript.words,
        "features": features,
    }


def attempt_evidence(rows, settings):
    if (
        sum(len(r["verbatim"]) + len(r["clean"]) + len(r["prompt_text"]) for r in rows)
        > settings.speaking_ai_max_input_characters
    ):
        raise ValueError("REPLAY_EVIDENCE_TOO_LARGE")
    return build_attempt_evidence(rows)
