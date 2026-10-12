"""Versioned private manifest and score-only result contracts."""

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.speaking_grading import CriterionBandScore, StrictDTO
from app.services.speaking_audio import fingerprint
from app.services.speaking_scorer import speaking_overall

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
Version = Annotated[str, Field(min_length=1, max_length=200)]
Reason = Literal[
    "MISSING_PREDICTION",
    "BENCHMARK_AUDIO_UNAVAILABLE",
    "BENCHMARK_EVIDENCE_INVALID",
    "BENCHMARK_PROCESSING_FAILED",
    "SPEAKING_AUDIO_UNASSESSABLE",
    "SPEAKING_PR_UNASSESSABLE",
    "SPEAKING_AI_PROVIDER_FAILED",
    "SPEAKING_AI_INVALID_SCORE",
    "SPEAKING_AI_FEEDBACK_FAILED",
    "SPEAKING_ASR_UNAVAILABLE",
    "SPEAKING_AI_NOT_CONFIGURED",
]


def band(value):
    return CriterionBandScore(score=value).score


class HumanLabels(StrictDTO):
    fc: float
    lr: float
    gra: float
    pr: float
    overall: float

    _bands = field_validator("fc", "lr", "gra", "pr", "overall", mode="before")(band)


class BenchmarkResponse(StrictDTO):
    audio_path: str | None = Field(default=None, min_length=1, max_length=2000)
    fixture_id: Identifier | None = None
    part_number: Literal[1, 2, 3]
    prompt_type: Literal["SHORT_ANSWER", "LONG_TURN", "FOLLOW_UP"]
    prompt_text: str = Field(min_length=1, max_length=10000)
    cue_points: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def local_source(self):
        if (self.audio_path is None) == (self.fixture_id is None):
            raise ValueError("One local source is required")
        if self.audio_path and ("://" in self.audio_path or "\0" in self.audio_path):
            raise ValueError("Local files only")
        if not self.prompt_text.strip():
            raise ValueError("Empty prompt")
        return self


class BenchmarkSample(StrictDTO):
    schema_version: Literal[1]
    id: Identifier
    responses: list[BenchmarkResponse] = Field(min_length=1, max_length=100)
    human: HumanLabels
    subgroups: dict[
        Literal[
            "recording_environment", "proficiency_bucket", "prompt_group", "microphone_quality"
        ],
        Identifier,
    ] = Field(default_factory=dict)
    assessor_version: Identifier | None = None
    test_reference: Identifier | None = None


class ScorerProvenance(StrictDTO):
    scorer: Literal["SpeakingScorer"] = "SpeakingScorer"
    provider: Version
    model: Version
    rubric_version: Version
    prompt_version: Version
    score_contract_version: Literal["half-band-v1"] = "half-band-v1"
    feedback_contract_version: Literal["bounded-feedback-v1"] = "bounded-feedback-v1"
    asr_provider: Version
    asr_model: Version
    asr_version: Version
    alignment_version: Version
    normalizer_version: Version
    quality_version: Version
    fluency_version: Version
    pronunciation_provider: Version
    pronunciation_version: Version
    pipeline_config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    implementation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    git_sha: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")


class Prediction(StrictDTO):
    id: Identifier
    scores: dict[Literal["fc", "lr", "gra", "pr"], float | None] = Field(default_factory=dict)
    reasons: dict[Literal["fc", "lr", "gra", "pr"], Reason] = Field(default_factory=dict)
    cache_key: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("scores", mode="before")
    @classmethod
    def half_bands(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Scores required")
        return {key: None if value is None else band(value) for key, value in values.items()}

    @property
    def overall(self):
        return speaking_overall(self.scores)[1]


class PredictionSet(StrictDTO):
    schema_version: Literal[1]
    provenance: ScorerProvenance
    predictions: list[Prediction] = Field(max_length=10000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({row.id for row in self.predictions}) != len(self.predictions):
            raise ValueError("Duplicate predictions")
        return self


def provenance(settings) -> ScorerProvenance:
    from app.providers.speaking_asr import provider_identity
    from app.providers.speaking_llm import config_identity
    from app.services.speaking_features import FEATURE_VERSION, feature_identity
    from app.services.speaking_quality import quality_identity

    llm, asr = config_identity(settings), provider_identity(settings)
    root = Path(__file__).resolve().parents[4]
    source = root / "backend/app"
    files = sorted(
        {
            path
            for pattern in (
                "services/speaking*.py",
                "providers/speaking*/*.py",
                "domains/scoring/speaking_prompts.py",
                "schemas/speaking*.py",
                "evaluation/speaking/*.py",
            )
            for path in source.glob(pattern)
        }
    )
    code_hash = fingerprint(
        {
            str(path.relative_to(source)).replace("\\", "/"): hashlib.sha256(
                path.read_text(encoding="utf-8").encode()
            ).hexdigest()
            for path in files
        }
    )
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        sha = sha if re.fullmatch(r"[a-f0-9]{40}", sha) else None
    except (OSError, subprocess.SubprocessError):
        sha = None
    return ScorerProvenance(
        provider=llm["provider"],
        model=llm["model"] or "unconfigured",
        rubric_version=settings.speaking_ai_rubric_version,
        prompt_version=settings.speaking_ai_prompt_version,
        asr_provider=asr["provider"],
        asr_model=asr["model"],
        asr_version=asr["version"],
        alignment_version="asr-word-timestamps-v1",
        normalizer_version=settings.speaking_normalizer_version,
        quality_version=settings.speaking_quality.version,
        fluency_version=FEATURE_VERSION,
        pronunciation_provider=(
            "alignment-acoustic-proxies"
            if settings.speaking_pronunciation_enabled
            else "unavailable"
        ),
        pronunciation_version=settings.speaking_pronunciation.version,
        pipeline_config_hash=fingerprint(
            [
                llm,
                asr,
                quality_identity(settings),
                feature_identity(settings),
                settings.speaking_normalizer_version,
                settings.speaking_max_decoded_seconds,
            ]
        ),
        implementation_hash=code_hash,
        git_sha=sha,
    )
