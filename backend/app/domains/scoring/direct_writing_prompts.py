"""Direct scoring reuses descriptor semantics, without an evidence-selection turn."""

import json

from app.domains.scoring.task1_prompts import score_prompt
from app.schemas.writing_ai import EvidenceResult

DIRECT_PROMPT_VERSION = "task1-direct-v1"


def direct_messages(request, trait, analysis):
    messages = score_prompt(request, trait, EvidenceResult(evidence=[]), analysis)
    payload = json.loads(messages[1]["content"])
    payload.pop("evidence")
    messages[1]["content"] = json.dumps(payload, ensure_ascii=False)
    messages[0]["content"] += "\nAssess the whole response directly in this one scoring turn."
    return messages
