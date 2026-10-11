"""Neutral prompt contracts and scripted profiles; never assert live model grades."""

import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from test_task1_visual import Task1FakeProvider, chart
from test_task1_visual import request as task1_request

from app.domains.scoring.essay_sources import segment_essay
from app.domains.scoring.mts_prompts import (
    DESCRIPTOR_FIT_GUIDANCE,
    LOW_BANDS,
    RUBRICS,
    SCOPES,
    TASK2_DESCRIPTOR_FIT_GUIDANCE,
    TRAIT_NAMES,
    evidence_messages,
    scoring_messages,
)
from app.domains.scoring.task1_prompts import (
    TASK1_BAND_PROFILES,
    TASK1_TRAIT_NAMES,
    evidence_prompt,
    score_prompt,
)
from app.domains.scoring.writing import WritingScoringRequest
from app.providers.writing_llm.base import Completion
from app.schemas.task1_claims import Task1Analysis
from app.schemas.writing_ai import TRAITS, Evidence, EvidenceResult
from app.services.mts_writing import MTSWritingScoringService
from app.services.task1_writing import Task1WritingScoringService

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "synthetic_writing_scoring_profiles.json").read_text(
        encoding="utf-8"
    )
)
PROFILES = FIXTURES["profiles"]


def request_for(task, profile):
    content = profile[f"task{task}"]
    if task == 1:
        req = task1_request()
        req.response = content["response"]
        return req
    return WritingScoringRequest(
        attempt_id=uuid4(),
        writing_task_id=uuid4(),
        prompt="Should fictional cities prioritise parks or housing? Discuss both and give your view.",
        response=content["response"],
    )


def messages_for(task, trait, stage):
    req = request_for(task, PROFILES[1])
    evidence = EvidenceResult(evidence=[])
    if task == 1:
        analysis = Task1Analysis(visual_family="chart_table", confidence="HIGH", reference=chart())
        return (
            evidence_prompt(req, trait, analysis)
            if stage == "evidence"
            else score_prompt(req, trait, evidence, analysis)
        )
    return (
        evidence_messages(req.prompt, req.response, trait)
        if stage == "evidence"
        else scoring_messages(req.prompt, req.response, trait, evidence)
    )


@pytest.mark.parametrize("task", [1, 2])
@pytest.mark.parametrize("trait", TRAITS)
def test_all_descriptor_anchors_and_symmetric_half_band_rule_remain(task, trait):
    system = messages_for(task, trait, "scoring")[0]["content"]
    profiles = TASK1_BAND_PROFILES[trait] if task == 1 else RUBRICS[trait] + " " + LOW_BANDS[trait]
    assert profiles in system
    assert all(f"{band}:" in profiles for band in range(1, 10))
    assert "official IELTS" in system and "May 2023" in system
    guidance = DESCRIPTOR_FIT_GUIDANCE if task == 1 else TASK2_DESCRIPTOR_FIT_GUIDANCE
    assert system.count(guidance) == 1
    if task == 2:
        assert "generated assessments do not participate in score inference" in system
        assert "Use retrieved evidence as representative support" not in system
    assert "Half-bands are interpolation between adjacent official whole-band descriptors" in system
    assert "when performance naturally falls between those profiles" in system
    assert "Do not favor the higher or lower band by default" in system
    assert system.count("Use the full 0–9 range") == 1
    assert system.count("Band 8 and Band 9 are valid outcomes") == 1
    assert system.count("Do not award a high band merely because") == 1
    assert "Bands 5–7 are not default outcomes" in system
    assert "Score 0 through 9 in increments of 0.5 only" in system
    assert "No score offsets, hard caps, error-count rules or cross-criterion penalties" in system


@pytest.mark.parametrize("task", [1, 2])
@pytest.mark.parametrize("trait", TRAITS)
@pytest.mark.parametrize("stage", ["evidence", "scoring"])
def test_prompts_do_not_request_directional_gates_or_blocker_feedback(task, trait, stage):
    system = messages_for(task, trait, stage)[0]["content"].lower()
    for removed in (
        "require sustained",
        "affirmative evidence",
        "a few good examples cannot",
        "a few strong sentences",
        "four paragraphs",
        "academic-looking words",
        "long sentences",
        "alone do not establish",
        "establish band 7",
        "higher profile",
        "next-higher",
        "next higher level",
        "next_band",
        "blocker",
        "high_band_justification",
        "minimum evidence",
        "consistency threshold",
        "prefer 8",
        "few errors means band 9",
        "human-quality language",
    ):
        assert removed not in system
    assert "vietnamese" in system and "hidden reasoning" in system
    assert "which next" not in system


@pytest.mark.parametrize("task", [1, 2])
@pytest.mark.parametrize("trait", TRAITS)
def test_retrieval_is_representative_without_strength_weakness_quota(task, trait):
    messages = messages_for(task, trait, "evidence")
    system = messages[0]["content"].lower()
    assert "representative evidence relevant to this criterion" in system
    assert "no fixed balance of strengths and weaknesses is required" in system
    assert "empty" in system and "allowed" in system
    assert "whole-band descriptors" not in system and "band 7" not in system
    assert DESCRIPTOR_FIT_GUIDANCE not in system
    payload = json.loads(messages[1]["content"])
    sources = segment_essay(request_for(task, PROFILES[1]).response)
    assert payload["allowed_ids"] == [source.source_id for source in sources]


@pytest.mark.parametrize("trait", TRAITS)
@pytest.mark.parametrize("stage", ["evidence", "scoring"])
def test_task2_scope_is_criterion_specific_for_evidence_feedback_and_scoring(trait, stage):
    system = messages_for(2, trait, stage)[0]["content"]
    assert SCOPES[trait] in system
    assert f"Criterion: {TRAIT_NAMES[trait]}." in system
    assert "Task Achievement" not in system
    for other in TRAITS:
        if other != trait:
            assert TRAIT_NAMES[other] not in system
            assert RUBRICS[other] not in system
    if stage == "scoring":
        assert "Return ONLY one field: score" in system


@pytest.mark.parametrize("task", [1, 2])
@pytest.mark.parametrize("trait", TRAITS)
def test_scoring_schema_exposes_only_core_output_and_no_extra_justification(task, trait):
    system = messages_for(task, trait, "scoring")[0]["content"]
    schema = json.loads(system.split("JSON schema: ", 1)[1])
    core = {"score"}
    assert set(schema["required"]) == set(schema["properties"]) == core
    assert schema["additionalProperties"] is False
    assert schema["properties"]["score"]["type"] == "number"


@pytest.mark.parametrize("trait", TRAITS)
def test_task2_score_prompt_is_independent_of_generated_evidence(trait):
    req = request_for(2, PROFILES[1])
    empty = EvidenceResult(evidence=[])
    unrelated = EvidenceResult(
        evidence=[
            Evidence(
                source_id="P1S1",
                quote="Fictional unrelated generated quote.",
                assessment="Nội dung do lượt lấy dẫn chứng tạo ra, không được ảnh hưởng điểm.",
            )
        ]
    )
    without_evidence = scoring_messages(req.prompt, req.response, trait, empty)
    assert scoring_messages(req.prompt, req.response, trait, unrelated) == without_evidence
    payload = json.loads(without_evidence[1]["content"])
    assert "evidence" not in payload
    assert payload["question"] == req.prompt
    assert payload["segmented_essay"] == "\n".join(
        f"[{source.source_id}] {source.text}" for source in segment_essay(req.response)
    )


def test_grounded_ta_inputs_support_understanding_without_count_to_band_mapping():
    for stage in ("evidence", "scoring"):
        system = messages_for(1, "ta", stage)[0]["content"].lower()
        assert "not additional scoring criteria" in system
        assert "do not convert counts of supported or contradicted claims" in system
        assert "omissions or comparisons into bands or penalties" in system


class ProfileProvider(Task1FakeProvider):
    """Scripted core results; inherited fake perception keeps the real Task 1 flow."""

    def __init__(self, task, profile, *, scores=None, evidence_count=None):
        super().__init__()
        self.task, self.profile = task, profile
        self.scores = profile["mock_scores"] if scores is None else scores
        self.evidence_count = (
            profile["evidence_count"] if evidence_count is None else evidence_count
        )
        self.mts_calls = []

    async def complete(self, messages, schema, *, options=None):
        properties = schema["properties"]
        if not {"evidence", "score", "feedback", "observations"} & properties.keys():
            return await super().complete(messages, schema, options=options)
        self.calls.append(messages)
        names = TASK1_TRAIT_NAMES if self.task == 1 else TRAIT_NAMES
        trait = next(t for t in TRAITS if f"Criterion: {names[t]}." in messages[0]["content"])
        stage = (
            "evidence"
            if "evidence" in properties
            else "scoring"
            if "score" in properties
            else "feedback"
        )
        self.mts_calls.append((trait, stage, messages, schema, options))
        summary = self.profile[f"task{self.task}"]["trait_profiles"][trait]
        if stage == "evidence":
            payload = json.loads(messages[1]["content"])
            output = {
                "evidence": [
                    {"source_id": source_id, "assessment": summary}
                    for source_id in payload["allowed_ids"][: self.evidence_count]
                ]
            }
        elif stage == "feedback" and self.task == 1:
            # These profiles exercise numeric descriptor fit, not chart/language
            # assertions. Empty structured explanations need no invented defects.
            output = {"observations": []}
        elif stage == "feedback" and self.task == 2:
            sources = segment_essay(self.profile["task2"]["response"])
            output = {
                "observations": [
                    {
                        "source_id": source.source_id,
                        "kind": "LIMITATION"
                        if self.profile["id"] in {"weak", "mid"}
                        else "STRENGTH",
                        "observation": summary,
                        "original_span": None,
                        "suggested_revision": None,
                        "confidence": "HIGH",
                    }
                    for source in sources[: self.evidence_count]
                ]
            }
        else:
            score = self.scores[trait]
            output = {
                "score": score,
                "feedback": f"Bài viết phù hợp khoảng Band {score} ở tiêu chí này. {summary}",
                # Empty lists are valid; no invented weaknesses/strengths gate the score.
                "strengths": [],
                "improvements": [],
            }
            output = {key: value for key, value in output.items() if key in properties}
        return Completion(json.dumps(output, ensure_ascii=False), finish_reason="stop")


async def assess_profile(task, profile, **provider_options):
    provider = ProfileProvider(task, profile, **provider_options)
    service = (Task1WritingScoringService if task == 1 else MTSWritingScoringService)(provider)
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    request = request_for(task, profile)
    result = await service.assess(request, trace)
    return result, service, provider, events, request


@pytest.mark.parametrize("task", [1, 2])
@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p["id"])
async def test_profiles_preserve_independent_scores_and_task_specific_inference_order(
    task, profile
):
    result, service, provider, events, req = await assess_profile(task, profile)
    assert result is not None and not service.failures and not service.diagnostics
    assert len(provider.calls) == (15 if task == 1 else 13)
    for trait in TRAITS:
        assert [stage for t, stage, *_ in provider.mts_calls if t == trait] == (
            ["evidence", "scoring", "feedback"]
            if task == 1
            else ["scoring", "evidence", "feedback"]
        )
    assert list(result.criteria.model_dump()) == list(TRAITS)
    assert set(
        payload.criterion for event, payload in events if event == "criterion.completed"
    ) == set(TRAITS)
    sources = segment_essay(req.response)
    for trait in TRAITS:
        criterion = getattr(result.criteria, trait)
        assert criterion.score == Decimal(str(profile["mock_scores"][trait]))
        assert criterion.feedback.strip()
        if task == 1:
            assert "Bài viết phù hợp khoảng Band" not in criterion.feedback
            assert criterion.strengths == criterion.improvements == []
        assert len(criterion.evidence) == profile["evidence_count"]
        assert [item.quote for item in criterion.evidence] == [
            source.text for source in sources[: profile["evidence_count"]]
        ]
    for trait, stage, messages, schema, options in provider.mts_calls:
        payload = json.loads(messages[1]["content"])
        assert all(
            f"[{source.source_id}] {source.text}" in payload["segmented_essay"]
            for source in sources
        )
        assert (
            not {"score", "criteria", "mock_scores", "trait_profiles", "human_scores"}
            & payload.keys()
        )
        assert "trait_profiles" not in str(messages) and "mock_scores" not in str(messages)
        if stage == "scoring":
            assert len(messages) == 2  # No other criterion's interaction or scores.
            assert options.max_tokens == 128
            assert set(schema["properties"]) == {"score"}
            if task == 2:
                assert "evidence" not in payload
        elif stage == "feedback":
            assert payload["fixed_score"] == profile["mock_scores"][trait]
            assert options.max_tokens == 1200
            assert set(schema["properties"]) == {"observations"}
        else:
            assert options.max_tokens == 1800
    assert result.raw_mean == sum(
        (Decimal(str(profile["mock_scores"][t])) for t in TRAITS), start=Decimal(0)
    ) / Decimal(4)


@pytest.mark.parametrize("task", [1, 2])
@pytest.mark.parametrize("score", [i / 2 for i in range(19)])
async def test_full_half_band_range_survives_without_evidence_minimum_or_metadata(task, score):
    result, service, provider, _events, _req = await assess_profile(
        task, PROFILES[1], scores=dict.fromkeys(TRAITS, score), evidence_count=0
    )
    assert result is not None and not service.diagnostics
    assert all(getattr(result.criteria, trait).score == Decimal(str(score)) for trait in TRAITS)
    assert result.raw_mean == result.overall_band == Decimal(str(score))
    assert len(provider.calls) == (15 if task == 1 else 13)
