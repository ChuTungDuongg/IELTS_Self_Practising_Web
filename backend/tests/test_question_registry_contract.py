"""Frontend question families must match backend validation and scoring support."""

import re
from pathlib import Path

from app.domains.questions.registry import question_registry


def test_frontend_question_type_union_matches_backend_registry() -> None:
    source = (Path(__file__).parents[2] / "frontend/src/features/questions/types.ts").read_text(
        encoding="utf-8"
    )
    declaration = re.search(r"export type QuestionType\s*=\s*(.*?);", source, re.DOTALL)
    assert declaration is not None
    frontend_types = set(re.findall(r'"([a-z_]+)"', declaration.group(1)))
    assert frontend_types == set(question_registry.names())
