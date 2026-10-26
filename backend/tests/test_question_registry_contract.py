"""Frontend question families must match backend validation and scoring support."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from app.domains.questions.normalization import normalize_question_group_payload
from app.domains.questions.numbering import question_slots
from app.domains.questions.registry import question_registry

CONTRACTS = json.loads(
    (Path(__file__).parent / "fixtures/question-contracts.json").read_text(encoding="utf-8")
)


def test_frontend_question_type_union_matches_backend_registry() -> None:
    source = (Path(__file__).parents[2] / "frontend/src/features/questions/types.ts").read_text(
        encoding="utf-8"
    )
    declaration = re.search(r"export type QuestionType\s*=\s*(.*?);", source, re.DOTALL)
    assert declaration is not None
    frontend_types = set(re.findall(r'"([a-z_]+)"', declaration.group(1)))
    assert frontend_types == set(question_registry.names())


def test_saved_contract_fixtures_cover_every_canonical_type():
    assert {case["group"]["question_type"] for case in CONTRACTS} == set(question_registry.names())


@pytest.mark.parametrize("case", CONTRACTS, ids=lambda case: case["group"]["question_type"])
def test_persisted_question_validation_response_score_and_identity_contract(case):
    original = deepcopy(case)
    group = case["group"]
    kind = group["question_type"]
    question = group["questions"][0]
    question_registry.validate(kind, group["config"], question["config"], question["answer_key"])
    assert (
        question_registry.validate_response(kind, case["response"], question["config"])
        == case["response"]
    )
    assert (
        question_registry.score(kind, question["answer_key"], case["response"], question["config"])
        == case["score"]
    )
    assert (
        question_registry.score(kind, question["answer_key"], case["wrong"], question["config"])
        == 0
    )
    assert list(question_slots(kind, 11, question["config"])) == list(range(11, 11 + case["score"]))
    config, questions = normalize_question_group_payload(
        question_type=kind,
        group_config=group["config"],
        questions=group["questions"],
        group_id=group["id"],
        passage_blocks=case["passageBlocks"],
    )
    repeated = normalize_question_group_payload(
        question_type=kind,
        group_config=config,
        questions=questions,
        group_id=group["id"],
        passage_blocks=case["passageBlocks"],
    )
    assert repeated == (config, questions)
    assert questions[0]["id"] == question["id"]
    assert questions[0]["answer_key"] == question["answer_key"]
    assert (
        question_registry.score(
            kind, questions[0]["answer_key"], case["response"], questions[0]["config"]
        )
        == case["score"]
    )
    if "options" in group["config"]:
        assert config["options"] == group["config"]["options"]
    assert case == original
