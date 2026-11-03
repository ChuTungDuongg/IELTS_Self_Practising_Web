"""Allowlisted persisted-run diagnostics; no prompt, essay or provider body."""

import re

from app.providers.writing_llm.base import safe_inference_attempts


def _band(value):
    if type(value) in {int, float} and 0 <= value <= 9 and value * 2 == int(value * 2):
        return float(value)
    return None


def _identifier(value):
    return (
        value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,200}", value) else None
    )


def _checksum(value):
    return value if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) else None


def run_diagnostics(run) -> dict:
    usage = run.usage_json if isinstance(run.usage_json, dict) else {}
    latency = usage.get("latency", {})
    latency = latency if isinstance(latency, dict) else {}
    stored = latency.get("ta_assessment", {})
    stored = stored if isinstance(stored, dict) else {}
    audit = {}
    if stored:
        audit = {
            "status": stored.get("status")
            if isinstance(stored.get("status"), str)
            and stored["status"]
            in {
                "NOT_RUN",
                "ASSESSING",
                "READY",
                "CONFLICT",
                "INSUFFICIENT_EVIDENCE",
                "UNREADABLE",
                "FAILED",
                "RECONCILING",
            }
            else None,
            "image_sha256": _checksum(stored.get("image_sha256")),
            "source_image_assessment": stored.get("source_image_assessment")
            if type(stored.get("source_image_assessment")) is bool
            else None,
            "validated_score": _band(stored.get("validated_score")),
            "reconciliations": stored.get("reconciliations")
            if type(stored.get("reconciliations")) is int and stored["reconciliations"] in {0, 1}
            else None,
            "conflict_kinds": [
                item
                for item in stored.get("conflict_kinds", [])
                if isinstance(item, str)
                and item
                in {
                    "NUMERIC",
                    "LABEL",
                    "UNIT",
                    "AXIS",
                    "LEGEND",
                    "COVERAGE",
                    "MAP",
                    "PROCESS",
                }
            ]
            if isinstance(stored.get("conflict_kinds"), list)
            else [],
        }
    attempts = []
    stages = latency.get("stages", {})
    for stage in stages.values() if isinstance(stages, dict) else []:
        if not isinstance(stage, dict) or not isinstance(stage.get("attempts"), list):
            continue
        for attempt in stage["attempts"][:4]:
            if isinstance(attempt, dict):
                attempts.extend(safe_inference_attempts(attempt.get("provider_attempts")))
    result = run.result_json if isinstance(run.result_json, dict) else {}
    criteria = result.get("criteria", {})
    ta = criteria.get("ta", {}) if isinstance(criteria, dict) else {}
    persisted = _band(ta.get("score")) if isinstance(ta, dict) else None
    validated = audit.get("validated_score")
    return {
        "diagnostic_version": "task1-ta-audit-v1",
        "provider": _identifier(run.provider),
        "model": _identifier(run.model),
        "prompt_version": _identifier(run.prompt_version),
        "input_fingerprint": _checksum(run.input_fingerprint),
        "status": _identifier(getattr(run.status, "value", run.status)),
        # Cache hits are create-run response metadata, not persisted on the run.
        # Absence must never be reported as a cache miss or a fresh inference.
        "cache_hit": None,
        "ta_assessment": audit or None,
        "provider_attempts": attempts[:256],
        "persisted_ta_score": persisted,
        "score_matches_assessment": persisted == validated
        if persisted is not None and validated is not None
        else None,
    }
