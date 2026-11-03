"""Real grading orchestration and OpenAI adapter with fictional HTTP responses."""

import json
from contextvars import ContextVar
from uuid import uuid4

import httpx
import pytest
import test_writing_ai as writing_cases
from test_openai_integration import intercept, settings

from app.providers.speaking_llm import create_provider as speaking_provider
from app.providers.writing_llm import create_provider

writing = writing_cases.writing


def wire(monkeypatch, fake, actual):
    output = ContextVar("fictional_openai_completion")
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "api.openai.com"
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "gpt-6-luna"}]})
        body = json.loads(request.content)
        completion, options = output.get()
        medium = options.task == "task1" and (
            options.stage in {"visual_grounding", "visual_reconciliation", "claim_verification"}
            or (options.stage in {"score", "scoring"} and options.criterion == "ta")
        )
        assert body["model"] == "gpt-6-luna"
        assert body["reasoning_effort"] == ("medium" if medium else "low")
        assert body["max_completion_tokens"] == (16384 if medium else 8192)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": completion.finish_reason,
                        "message": {"content": completion.text},
                    }
                ],
                "usage": completion.usage,
            },
        )

    intercept(monkeypatch, handler)

    class Adapter:
        task1_image_assessment = getattr(actual, "task1_image_assessment", False)
        reasoned_inference = True
        run_timeout_seconds = getattr(actual, "run_timeout_seconds", None)

        async def ensure_ready(self):
            await actual.ensure_ready()

        async def complete(self, messages, schema, *, options=None):
            token = output.set((await fake.complete(messages, schema, options=options), options))
            try:
                return await actual.complete(messages, schema, options=options)
            finally:
                output.reset(token)

    return Adapter(), requests


@pytest.mark.parametrize("task", [1, 2])
async def test_writing_task_pipelines_preserve_validated_results_through_openai_http(
    monkeypatch, task
):
    from test_writing_ai import ESSAY, FakeProvider

    from app.domains.scoring.writing import WritingScoringRequest
    from app.services.mts_writing import MTSWritingScoringService

    if task == 1:
        from test_openai_task1_assessment import SourceImageProvider
        from test_task1_visual import request

        from app.services.task1_writing import Task1WritingScoringService

        fake, data, service = SourceImageProvider(), request(), Task1WritingScoringService
    else:
        fake, service = FakeProvider(), MTSWritingScoringService
        data = WritingScoringRequest(
            attempt_id=uuid4(),
            writing_task_id=uuid4(),
            prompt="Discuss fictional city parks.",
            response=ESSAY,
            paragraph_mode="textarea",
        )
    provider, requests = wire(monkeypatch, fake, create_provider(settings()))
    await provider.ensure_ready()
    events = []

    async def trace(event, payload):
        events.append((event, payload))

    result = await service(provider).assess(data, trace)
    assert result is not None and result.overall_band is not None
    bodies = [json.loads(request.content) for request in requests if request.method == "POST"]
    feedback_bodies = [body for body in bodies if body.get("stream")]
    assert len(feedback_bodies) == 4
    assert all(body["stream_options"] == {"include_usage": True} for body in feedback_bodies)
    previews = [payload for kind, payload in events if kind == "criterion.feedback.draft"]
    assert previews and all(payload.result is None for payload in previews)
    assert set(result.criteria.model_dump()) == {"ta", "cc", "lr", "gra"}
    assert sum(event == "criterion.completed" for event, _ in events) >= 4
    assert any(request.method == "POST" for request in requests)
    if task == 1:
        import base64

        bodies = [json.loads(r.content) for r in requests if r.method == "POST"]
        visual = [body for body in bodies if isinstance(body["messages"][1]["content"], list)]
        assert len(visual) == 2, "Grounding and TA must both contain actual image bytes"
        for body in visual:
            image_url = body["messages"][1]["content"][1]["image_url"]
            assert image_url["detail"] == "high"
            assert base64.b64decode(image_url["url"].split(",", 1)[1]) == data.image.data
            assert body["reasoning_effort"] == "medium" and body["max_completion_tokens"] == 16384
        assert "conflicts" in visual[1]["messages"][0]["content"]
        assert fake.assessment_calls == 1


async def test_speaking_all_criteria_keep_parts_acoustics_and_score_checkpoints(monkeypatch):
    from test_speaking_ai import FEEDBACK, FakeProvider, evidence, feature_bundle

    from app.services.speaking_scorer import SpeakingScorer, speaking_overall

    fake = FakeProvider(*[value for _ in range(4) for value in ({"score": 6.5}, FEEDBACK)])
    provider, requests = wire(monkeypatch, fake, speaking_provider(settings()))
    scorer = SpeakingScorer(provider)
    saved, results = [], {}

    async def checkpoint(result):
        assert result.status == "SCORE_READY"
        saved.append(result)

    for criterion in ("fc", "lr", "gra", "pr"):
        result = await scorer.score_criterion(
            criterion, evidence(features=feature_bundle()), checkpoint
        )
        assert result.status == "COMPLETED" and result.score == 6.5
        results[criterion] = result.score
    assert len(saved) == 4 and len(requests) == 8
    assert speaking_overall(results) == (6.5, 6.5)
    serialized = "\n".join(request.content.decode() for request in requests)
    assert "PRIVATE_SCRATCH_MARKER" not in serialized and "/private/audio.webm" not in serialized


@pytest.mark.integration
async def test_openai_worker_persists_identity_and_invalidates_cache_without_touching_human_score(
    monkeypatch, db_session, writing
):
    from sqlalchemy import select
    from test_writing_ai import FakeProvider, worker

    from app.models import AttemptWritingScore
    from app.services.writing_ai import WritingAIService

    config = settings()
    api = WritingAIService(db_session, db_session.info["current_user_id"], config)
    provider, requests = wire(monkeypatch, FakeProvider(), create_provider(config))
    created = await api.create(writing[0], writing[2], force=False)
    await worker(db_session, config, provider).execute(created.run_id)
    saved = await api.get(created.run_id)
    assert saved.status == "COMPLETED" and (saved.provider, saved.model) == ("openai", "gpt-6-luna")
    assert (await api.create(writing[0], writing[2], force=False)).run_id == saved.id
    config.ai_writing_openai_max_output_tokens = 16384
    assert (await api.create(writing[0], writing[2], force=False)).run_id != saved.id
    async with db_session.begin():
        score = await db_session.scalar(
            select(AttemptWritingScore).where(AttemptWritingScore.attempt_id == writing[0])
        )
        assert score.ta == 7 and score.ta_feedback == "Human feedback stays."
    assert any(request.method == "POST" for request in requests)
