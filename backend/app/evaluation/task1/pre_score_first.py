"""Retain the v7/v8 benchmark contract while production uses score-only output.

The descriptor context is unchanged by v9; the combined-output instructions are
from the frozen v5 baseline. Production never selects this evaluation service.
"""

from app.evaluation.task1.baseline_v5_prompts import score_prompt as combined_score_prompt
from app.schemas.writing_ai import RawScoringOutput
from app.services.task1_writing import Task1WritingScoringService


class PreScoreFirstTask1WritingScoringService(Task1WritingScoringService):
    score_schema = RawScoringOutput

    def _score_prompt(self, request, trait, evidence, analysis):
        messages = super()._score_prompt(request, trait, evidence, analysis)
        combined = combined_score_prompt(request, trait, evidence, analysis)
        boundary = "Score 0 through 9"
        messages[0]["content"] = (
            messages[0]["content"].split(boundary, 1)[0]
            + boundary
            + combined[0]["content"].split(boundary, 1)[1]
        )
        return messages
