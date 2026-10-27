from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import AttemptScope, ModuleType
from app.schemas.attempts import FocusedUnit


class AssignmentTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["MODULE", "FULL_MOCK"]
    module: ModuleType | None = None
    scope: AttemptScope = AttemptScope.FULL_MODULE
    focused_unit: FocusedUnit | None = None

    @model_validator(mode="after")
    def coherent(self):
        if self.mode == "FULL_MOCK":
            if self.module or self.focused_unit or self.scope != AttemptScope.FULL_MODULE:
                raise ValueError("Full Mock cannot select a module or focused unit")
        elif self.module is None:
            raise ValueError("Select the assigned module")
        elif (self.scope == AttemptScope.FOCUSED_UNIT) != (self.focused_unit is not None):
            raise ValueError("Focused assignments require exactly one unit")
        if self.focused_unit and self.focused_unit.kind == "SPEAKING_PART":
            raise ValueError("Speaking Part is not supported for classroom assignments")
        return self
