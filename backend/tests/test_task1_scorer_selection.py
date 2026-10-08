import pytest
from pydantic import ValidationError
from test_tacs_tree import snapshot
from test_task1_visual import Task1FakeProvider, request

from app.core.config import Settings
from app.core.exceptions import AppError
from app.services.task1_scorer import Task1ExecutionConfig, create_task1_scorer
from app.services.writing_ai import input_fingerprint


def test_selector_default_and_bounded_budget():
    settings = Settings(_env_file=None)
    assert settings.ai_writing_task1_scorer == "anchor_pairwise"
    for budget in (0, 4):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, ai_writing_pairwise_max_tree_nodes=budget)
    for architecture, name in [
        ("mts", "Task1WritingScoringService"),
        ("direct", "Task1DirectScoringService"),
        ("anchor_pairwise", "Task1TACSScoringService"),
    ]:
        execution = Task1ExecutionConfig.pin(architecture, snapshot(), 2)
        scorer = create_task1_scorer(
            execution, snapshot(), Task1FakeProvider(), target_fingerprint="test"
        )
        assert type(scorer).__name__ == name


def test_fingerprint_includes_execution_and_exact_task_identity():
    target = request()
    config = Task1ExecutionConfig.pin("anchor_pairwise", snapshot(), 2)
    original = input_fingerprint(target, config.prompt_version, "fake", "test", execution=config)
    for update in (
        {"max_tree_nodes": 3},
        {"anchor_set_version": 2},
        {"pairwise_prompt_version": "new"},
    ):
        assert (
            input_fingerprint(
                target,
                config.prompt_version,
                "fake",
                "test",
                execution=config.model_copy(update=update),
            )
            != original
        )
    assert (
        input_fingerprint(
            target.model_copy(update={"writing_task_id": __import__("uuid").uuid4()}),
            config.prompt_version,
            "fake",
            "test",
            execution=config,
        )
        != original
    )


@pytest.mark.parametrize("architecture", ["mts", "direct", "anchor_pairwise"])
@pytest.mark.parametrize("field", [
    "prompt_version", "direct_prompt_version", "pairwise_prompt_version",
    "feedback_prompt_version", "visual_contract_version",
])
def test_unsupported_pinned_contract_is_rejected_before_scoring(architecture, field):
    execution = Task1ExecutionConfig.pin(architecture, snapshot(), 2)
    provider = Task1FakeProvider()
    with pytest.raises(AppError) as error:
        create_task1_scorer(
            execution.model_copy(update={field: "unsupported-historical-contract"}),
            snapshot(), provider, target_fingerprint="test",
        )
    assert error.value.code == "AI_CONFIGURATION_CHANGED"
    assert provider.calls == []


def test_null_legacy_execution_still_uses_mts():
    scorer = create_task1_scorer(
        None, snapshot(), Task1FakeProvider(), target_fingerprint="legacy"
    )
    assert type(scorer).__name__ == "Task1WritingScoringService"
