"""Task 1 diagnostic paths are application schema names, never provider data."""

from typing import get_args

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorType

from app.schemas.task1_visual import VisualInvariantError
from app.schemas.writing_ai import ValidationIssue


def safe_task1_issues(error: ValidationError, schema: type[BaseModel]) -> list[ValidationIssue]:
    contract = schema.model_json_schema()
    fields = set(contract.get("properties", {}))
    for definition in contract.get("$defs", {}).values():
        fields.update(definition.get("properties", {}))
    # These are fixed discriminator branch names, not fields or chart labels.
    branches = {
        "chart_table",
        "process",
        "map",
        "system",
        "other",
        "numeric",
        "comparison",
        "relation",
    }
    types = {*get_args(ErrorType), *get_args(VisualInvariantError)}
    issues = []
    for item in error.errors(include_url=False, include_context=False, include_input=False)[:8]:
        path = []
        for part in item["loc"]:
            if type(part) is int and part >= 0:
                path.append(str(part))
            elif part in fields:
                path.append(part)
            elif part in branches:
                continue
            else:
                path.append("<extra>")
                break
        issues.append(
            ValidationIssue(
                field=".".join(path)[:120] or "<root>",
                validation_type=item["type"] if item["type"] in types else "validation_error",
            )
        )
    return issues


class WrongVisualFamily(ValueError):
    """Fixed semantic failure classification without storing the rejected family."""
