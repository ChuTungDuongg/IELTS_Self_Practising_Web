"""DEV-only single-variable experiment; never selects a production prompt."""

import json

from app.evaluation.task1.manifest import BenchmarkInputError
from app.services.task1_writing import Task1WritingScoringService


class SourceIdsOnlyTask1Scorer(Task1WritingScoringService):
    """Keep full essay, original image, rubric, facts and claims at TA scoring."""

    def _score_prompt(self, request, trait, evidence, analysis):
        messages = super()._score_prompt(request, trait, evidence, analysis)
        if trait != "ta":
            return messages
        # Source-image assessment has a text part followed by the original ImagePart.
        # Change only the free-form assessments, keeping source IDs and quotations
        # in segmented_essay. Evidence selection and feedback remain identical.
        content = messages[1]["content"]
        payload = json.loads(content[0]["text"])
        payload["evidence"] = [{"source_id": item["source_id"]} for item in payload["evidence"]]
        content[0] = {**content[0], "text": json.dumps(payload, ensure_ascii=False)}
        return messages


def evidence_configurations(settings):
    from app.evaluation.task1.runner import configurations

    if settings.ai_writing_provider != "openai" or settings.ai_writing_openai_model != "gpt-6-luna":
        raise BenchmarkInputError("BENCHMARK_EVIDENCE_ABLATION_REQUIRES_LUNA")
    if not settings.ai_writing_openai_task1_image_assessment:
        raise BenchmarkInputError("BENCHMARK_EVIDENCE_ABLATION_REQUIRES_SOURCE_IMAGE")
    base = configurations(settings, "v12", "off")[0]
    return [
        base.model_copy(
            update={
                "label": f"task1-ta-evidence-{mode}:DEV",
                "ta_evidence_mode": mode,
            }
        )
        for mode in ("selector_assessments", "source_ids_only")
    ]
