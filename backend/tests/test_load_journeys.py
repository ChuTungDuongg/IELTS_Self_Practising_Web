"""The generator must fail if save acknowledgement or finalized review loses data."""

import pytest
from benchmarks.load.contracts import ContractFailure
from benchmarks.load.journeys import review, save_objective


def objective_api(*, bad_save=False):
    calls = []
    questions = [{"id": f"q{i}", "answer_revision": 0} for i in range(40)]

    def api(method, path, name, **kwargs):
        calls.append((name, kwargs))
        if name == "attempt.exam":
            return {"passages": [{"id": "p1", "question_groups": [{"questions": questions}]}]}
        if name == "answer.autosave":
            body = kwargs["json"]
            return {
                "revision": body["expected_revision"] + 1,
                "value": "lost" if bad_save else body["value"],
                "is_correct": True,
            }
        return {}

    return api, calls


def test_objective_journey_navigates_and_retains_every_expected_answer():
    api, calls = objective_api()
    expected = save_objective(api, lambda _: None, "a1")
    assert expected == {f"q{i}": "fixture" for i in range(40)}
    assert any(name == "attempt.navigation" for name, _ in calls)


def test_objective_journey_rejects_acknowledged_value_loss():
    api, _ = objective_api(bad_save=True)
    with pytest.raises(ContractFailure, match="ANSWER_VALUE_MISMATCH"):
        save_objective(api, lambda _: None, "a1")


def test_review_compares_saved_answers_including_missing_rows():
    def api(*_, **__):
        return {
            "attempt": {"status": "SUBMITTED"},
            "answers": [{"question_id": "q1", "value": "lost"}],
        }

    with pytest.raises(ContractFailure, match="REVIEW_ANSWER_MISMATCH"):
        review(api, "a1", {"q1": "fixture", "q2": "fixture"})
