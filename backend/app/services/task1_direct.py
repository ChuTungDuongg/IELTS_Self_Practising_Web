from app.domains.scoring.direct_writing_prompts import direct_messages
from app.domains.scoring.essay_sources import segment_essay
from app.schemas.writing_ai import CriterionResult, EvidenceResult, RawScoringOutput
from app.services.task1_writing import Task1WritingScoringService


class Task1DirectScoringService(Task1WritingScoringService):
    """Same grounded TA dependencies and failure isolation; one scoring turn per trait."""

    def scoring_metadata(self):
        return {
            "architecture": "direct",
            "criteria": {
                t: {"mode": "GROUNDED_DIRECT" if t == "ta" else "DIRECT"} for t in self.states
            },
        }

    def _evidence_prompt(self, request, trait, analysis):
        return []

    def _score_prompt(self, request, trait, evidence, analysis):
        return direct_messages(request, trait, analysis)

    async def assess_criterion(self, request, trait, trace, evidence_prompt, score_prompt):
        sources = {s.source_id: s for s in segment_essay(request.response)}
        score = await self._validated(
            score_prompt(EvidenceResult(evidence=[])),
            RawScoringOutput,
            sources,
            trait,
            "scoring",
            trace,
        )
        return CriterionResult(**score.model_dump(exclude={"calibration"}), evidence=[])
