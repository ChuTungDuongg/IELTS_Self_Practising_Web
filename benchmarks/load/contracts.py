"""HTTP payloads mirror the canonical Pydantic API schemas, tested together."""


class ContractFailure(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractFailure(code)


def assert_key_free(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "answer_key",
                "accepted",
                "correct_answer",
                "correct_answers",
            }:
                raise ContractFailure("ACTIVE_KEY_LEAK")
            assert_key_free(item)
    elif isinstance(value, list):
        for item in value:
            assert_key_free(item)


def attempt_payload(version: str, module: str) -> dict:
    return {"test_version_id": version, "module": module, "timer": {"mode": "COUNT_UP"}}


def mock_payload(version: str) -> dict:
    return {"test_version_id": version}


def answer_payload(value, revision: int) -> dict:
    return {"value": value, "expected_revision": revision}


def writing_payload(content: str, revision: int) -> dict:
    return {"content": content, "expected_revision": revision}
