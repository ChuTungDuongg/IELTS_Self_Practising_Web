"""Grounded Direct TA; deterministic language scores and independent feedback."""

import json

from app.domains.scoring.tacs import TACSTree
from app.domains.scoring.task1_prompts import DATA_GUARD, criterion_guidance
from app.providers.writing_llm.base import CompletionOptions, validate_finish
from app.schemas.tacs import ComparisonResponse, FeedbackSynthesis
from app.schemas.writing_ai import CriterionResult, EventPayload
from app.services.task1_direct import Task1DirectScoringService
from app.services.writing_execution import TraceFailure
from app.services.writing_pairwise import PairwiseComparator

HYBRID_PROMPT_VERSION = "task1-hybrid-tacs-v1"
FEEDBACK_PROMPT_VERSION = "task1-tacs-feedback-v1"


class Task1TACSScoringService(Task1DirectScoringService):
    def __init__(
        self,
        provider,
        chart_derenderer=None,
        chart_timeout=90,
        *,
        anchor_snapshot,
        target_fingerprint,
        max_tree_nodes=2,
        **kwargs,
    ):
        super().__init__(provider, chart_derenderer, chart_timeout, **kwargs)
        self.anchor_snapshot = anchor_snapshot
        self.target_fingerprint = target_fingerprint
        self.max_tree_nodes = max_tree_nodes
        self.metadata = {}

    def scoring_metadata(self):
        return {
            "architecture": "anchor_pairwise",
            "anchor_set_id": str(self.anchor_snapshot.id) if self.anchor_snapshot.id else None,
            "anchor_set_version": self.anchor_snapshot.version,
            "node_budget": self.max_tree_nodes,
            "criteria": self.metadata,
        }

    async def assess(self, request, trace):
        self.metadata = {}
        await super().assess(request, trace)
        protected = self.protected_trace(trace)
        selected = {
            t: self.states[t].result
            for t in ("cc", "lr", "gra")
            if self.metadata.get(t, {}).get("mode") == "PAIRWISE"
        }
        if selected:
            # Scores are already final and checkpointed; feedback cannot rescore them.
            try:
                with self.latency.stage("feedback"):
                    completion = await self.provider.complete(
                        [
                            {
                                "role": "system",
                                "content": f"{DATA_GUARD}\nProvide concise Vietnamese feedback for only the requested language criteria. Do not score, revise scores or return score fields. "
                                + " ".join(criterion_guidance(t) for t in selected),
                            },
                            {
                                "role": "user",
                                "content": json.dumps(
                                    {
                                        "question": request.prompt,
                                        "response": request.response,
                                        "criteria": {
                                            t: float(r.score) for t, r in selected.items()
                                        },
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        ],
                        FeedbackSynthesis.model_json_schema(),
                        options=CompletionOptions(max_tokens=4096),
                    )
                    self.aux_usage.append(completion.usage)
                    validate_finish(completion.finish_reason)
                    feedback = FeedbackSynthesis.model_validate_json(completion.text)
                    if set(feedback.criteria) != set(selected):
                        raise ValueError("Feedback criteria do not match")
            except TraceFailure:
                raise
            except Exception:
                for t in selected:
                    self.metadata[t]["feedback_status"] = "UNAVAILABLE"
            else:
                for t, item in feedback.criteria.items():
                    self.states[t].result = CriterionResult(
                        score=selected[t].score, evidence=[], **item.model_dump()
                    )
                    self.metadata[t]["feedback_status"] = "AVAILABLE"
            for t in selected:
                await protected(
                    "criterion.completed", EventPayload(criterion=t, result=self.states[t].result)
                )
        return self._task1_result(self.analysis)

    def _task1_result(self, analysis):
        self.analysis = analysis
        return super()._task1_result(analysis)

    async def _task1_criterion(self, request, trait, analysis, trace):
        if trait == "ta":
            self.metadata[trait] = {"mode": "GROUNDED_DIRECT"}
            return await super()._task1_criterion(request, trait, analysis, trace)
        state = self.states[trait]
        state.stage = "pairwise"
        await trace("criterion.started", EventPayload(criterion=trait))
        comparator = PairwiseComparator(self.provider, usage=state.usage)
        tree = TACSTree(comparator, self.max_tree_nodes)

        async def event(name):
            self.metadata[trait] = {
                "mode": "SEARCHING",
                "tree": tree.progress.model_dump(mode="json"),
                "pairwise_calls": tree.progress.pairwise_calls,
            }
            await trace(name, EventPayload(criterion=trait, stage="pairwise"))

        with self.latency.stage("pairwise", trait):
            outcome = await tree.score(
                self.anchor_snapshot,
                1,
                trait,
                ComparisonResponse(task_prompt=request.prompt, response_text=request.response),
                self.target_fingerprint,
                on_event=event,
            )
        self.metadata[trait] = {
            "mode": "PAIRWISE" if outcome.score is not None else "DIRECT_FALLBACK",
            "fallback_reason": outcome.fallback_reason,
            "tree": outcome.model_dump(mode="json"),
            "pairwise_calls": outcome.pairwise_calls,
        }
        if outcome.score is None:
            return await super()._task1_criterion(request, trait, analysis, trace)
        state.result = CriterionResult(
            score=outcome.score,
            evidence=[],
            feedback=None,
            strengths=[],
            improvements=[],
            feedback_status="UNAVAILABLE",
            feedback_error_code="AI_FEEDBACK_UNAVAILABLE",
        )
        self.latency.completed_criterion()
        await trace("criterion.completed", EventPayload(criterion=trait, result=state.result))
        return state.result
