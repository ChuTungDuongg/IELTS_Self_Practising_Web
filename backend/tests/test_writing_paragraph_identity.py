"""Textarea line breaks retain paragraph identity without rewriting saved essays."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.domains.scoring import essay_sources
from app.domains.scoring.writing import WritingScoringRequest
from app.domains.scoring.writing_relevance import relevance_messages
from app.models import Attempt, AttemptWritingResponse, WritingTask
from app.models.enums import AttemptScope, AttemptStatus, ModuleType, TimerMode
from app.providers.writing_llm.base import Completion
from app.schemas.attempts import WritingResponseUpdate
from app.services.task1_input import Task1ScoringRequest
from app.services.writing_ai import WritingAIService
from app.services.writing_execution import WritingLatencyMetrics
from app.services.writing_relevance import classify_relevance


class PersistedWritingRepository:
    """Only the database boundary is substituted; production input stays real."""

    def __init__(self, attempt, task, response):
        self.saved_attempt = attempt
        self.saved_task = task
        self.saved_response = response

    async def attempt(self, attempt_id, user_id, *, lock=False):
        if (attempt_id, user_id) == (self.saved_attempt.id, self.saved_attempt.user_id):
            return self.saved_attempt
        return None

    async def task(self, task_id, version_id):
        if (task_id, version_id) == (self.saved_task.id, self.saved_attempt.test_version_id):
            return self.saved_task
        return None

    async def essay(self, attempt_id, task_id):
        if (attempt_id, task_id) == (
            self.saved_response.attempt_id,
            self.saved_response.writing_task_id,
        ):
            return self.saved_response.content
        return ""


async def production_input(content, *, task_number=2, require_essay=True):
    # This is the JSON body used by saveWritingResponse's PUT, decoded through
    # the real API schema and held in the authoritative persistence model.
    update = WritingResponseUpdate.model_validate_json(
        json.dumps({"content": content, "expected_revision": 0}, ensure_ascii=False)
    )
    attempt = Attempt(
        id=uuid4(),
        user_id=uuid4(),
        test_version_id=uuid4(),
        module_type=ModuleType.WRITING,
        status=AttemptStatus.SUBMITTED,
        scope=AttemptScope.FULL_MODULE,
        timer_mode=TimerMode.COUNT_UP,
        finished_at=datetime.now(UTC),
        test_session_id=None,
    )
    task = WritingTask(
        id=uuid4(),
        task_number=task_number,
        prompt="Discuss fictional parks.",
        order_index=0,
        task_type="LINE_GRAPH" if task_number == 1 else None,
    )
    response = AttemptWritingResponse(
        attempt_id=attempt.id,
        writing_task_id=task.id,
        content=update.content,
        word_count=len(update.content.split()),
        revision=1,
    )
    service = WritingAIService(None, attempt.user_id, Settings(_env_file=None))
    service.repository = PersistedWritingRepository(attempt, task, response)
    request = await service.input(attempt.id, task.id, require_essay=require_essay)
    return request, response


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
async def test_task2_saved_enter_is_a_paragraph_boundary_in_production_input(newline):
    content = f"  Same.  Same.{newline}Same.{newline}{newline}“Costs” matter–too.  "
    request, stored = await production_input(content)
    payload = json.loads(relevance_messages(request)[1]["content"])
    assert request.response == stored.content == content
    assert payload["allowed_ids"] == ["P1S1", "P1S2", "P2S1", "P3S1"]
    assert payload["segmented_essay"] == (
        "[P1S1] Same.\n[P1S2] Same.\n[P2S1] Same.\n[P3S1] “Costs” matter–too."
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
async def test_relevance_prompt_and_resolver_share_saved_paragraph_source_ids(newline):
    content = f"First fictional idea.{newline}Second fictional idea."
    request, _ = await production_input(content)

    class Provider:
        payload = None

        async def complete(self, messages, schema, *, options=None):
            self.payload = json.loads(messages[1]["content"])
            return Completion(
                json.dumps(
                    {
                        "verdict": "ON_TOPIC",
                        "confidence": "HIGH",
                        "source_ids": ["P2S1"],
                        "reason": "Ý thứ hai liên quan đến đề bài.",
                    }
                )
            )

    events, diagnostics, usage = [], [], []

    async def trace(event, payload):
        events.append((event, payload))

    provider = Provider()
    result = await classify_relevance(
        provider, request, None, trace, usage, diagnostics, WritingLatencyMetrics()
    )
    assert result is not None
    assert provider.payload["allowed_ids"] == ["P1S1", "P2S1"]
    assert result.evidence[0].source_id == "P2S1"
    assert result.evidence[0].quote == "Second fictional idea."
    assert not diagnostics
    assert [event for event, _ in events] == ["relevance.started", "relevance.completed"]


@pytest.mark.parametrize(
    "newline,expected_spans",
    [
        ("\n", [(2, 7), (9, 14), (15, 20), (22, 41)]),
        ("\r\n", [(2, 7), (9, 14), (16, 21), (25, 44)]),
    ],
)
async def test_request_sources_keep_exact_repeated_sentence_offsets(newline, expected_spans):
    content = f"  Same.  Same.{newline}Same.{newline}{newline}“Costs” matter–too.  "
    request, stored = await production_input(content)
    segments = essay_sources.request_sources(request)
    assert [(s.source_id, s.paragraph_index, s.sentence_index) for s in segments] == [
        ("P1S1", 1, 1),
        ("P1S2", 1, 2),
        ("P2S1", 2, 1),
        ("P3S1", 3, 1),
    ]
    assert [(s.start, s.end) for s in segments] == expected_spans
    assert [s.text for s in segments] == ["Same.", "Same.", "Same.", "“Costs” matter–too."]
    assert all(stored.content[s.start : s.end] == s.text for s in segments)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_default_blank_lines_keep_single_newline_as_wrapped_sentence(newline):
    content = f"A fictional sentence wraps{newline}without punctuation.{newline}{newline}Second."
    request = WritingScoringRequest(
        attempt_id=uuid4(), writing_task_id=uuid4(), prompt="Fictional prompt.", response=content
    )
    assert [(s.source_id, s.text) for s in essay_sources.segment_essay(content)] == [
        ("P1S1", f"A fictional sentence wraps{newline}without punctuation."),
        ("P2S1", "Second."),
    ]
    assert [(s.source_id, s.text) for s in essay_sources.request_sources(request)] == [
        ("P1S1", f"A fictional sentence wraps{newline}without punctuation."),
        ("P2S1", "Second."),
    ]


async def test_visual_softwrap_without_newline_does_not_invent_paragraphs():
    content = "Fictional parks " + "help communities " * 30 + "daily. Costs matter."
    request, stored = await production_input(content)
    sources = essay_sources.request_sources(request)
    assert [(s.source_id, s.paragraph_index) for s in sources] == [("P1S1", 1), ("P1S2", 1)]
    assert sources[0].text == "Fictional parks " + "help communities " * 30 + "daily."
    assert all(stored.content[s.start : s.end] == s.text for s in sources)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
async def test_task1_production_input_preserves_four_editor_paragraphs(newline):
    content = newline.join(["Introduction.", "Overview.", "Earlier details.", "Later details."])
    request, stored = await production_input(content, task_number=1, require_essay=False)
    assert isinstance(request, Task1ScoringRequest)
    assert request.paragraph_mode == "textarea" and request.response == stored.content == content
    assert [(s.source_id, s.text) for s in essay_sources.request_sources(request)] == [
        ("P1S1", "Introduction."),
        ("P2S1", "Overview."),
        ("P3S1", "Earlier details."),
        ("P4S1", "Later details."),
    ]


async def test_paragraph_mode_is_internal_and_absent_from_serialized_requests():
    request, _ = await production_input("One.\nTwo.")
    assert request.paragraph_mode == "textarea"
    assert "paragraph_mode" not in request.model_dump()
    assert "paragraph_mode" not in json.loads(request.model_dump_json())
    assert "paragraph_mode" not in request.model_json_schema(mode="serialization")["properties"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
async def test_all_production_task1_stages_resolve_the_same_saved_sources(newline):
    from test_task1_visual import PNG, Task1FakeProvider

    from app.providers.writing_llm.base import ImagePart
    from app.services.task1_writing import Task1WritingScoringService

    content = newline.join(
        ["Introduction. Same.", "Overview.", "A increased from 20 to 50.", "Same."]
    )
    req, stored = await production_input(content, task_number=1, require_essay=False)
    req.image = ImagePart("image/png", PNG)
    sources = essay_sources.request_sources(req)
    expected = [s.source_id for s in sources]

    class Provider(Task1FakeProvider):
        async def complete(self, messages, schema, *, options=None):
            if "claims" in schema["properties"]:
                reply = await super().complete(messages, schema, options=options)
                data = json.loads(reply.text)
                data["claims"][0]["source_ids"] = ["P3S1"]
                return Completion(json.dumps(data))
            if "evidence" in schema["properties"]:
                self.calls.append(messages)
                return Completion(
                    json.dumps(
                        {
                            "evidence": [
                                {
                                    "source_id": identity,
                                    "assessment": "Unverified selector commentary.",
                                }
                                for identity in ("P1S1", "P2S1", "P3S1", "P4S1")
                            ]
                        }
                    )
                )
            if "observations" in schema["properties"]:
                self.calls.append(messages)
                return Completion(json.dumps({"observations": []}))
            return await super().complete(messages, schema, options=options)

    events = []

    async def trace(event, payload):
        events.append((event, payload))

    provider = Provider()
    result = await Task1WritingScoringService(provider).assess(req, trace)
    assert result is not None
    assert expected == ["P1S1", "P1S2", "P2S1", "P3S1", "P4S1"]
    assert stored.content == req.response == content
    assert all(content[s.start : s.end] == s.text for s in sources)
    claim = result.task1_analysis.claims[0]
    assert claim.verdict == "SUPPORTED" and claim.source_ids == ["P3S1"]
    assert claim.quote == "A increased from 20 to 50."
    for call in provider.calls:
        if not isinstance(call[1]["content"], str):
            continue
        payload = json.loads(call[1]["content"])
        if "segmented_essay" in payload:
            assert payload["segmented_essay"] == "\n".join(
                f"[{s.source_id}] {s.text}" for s in sources
            )
        if "allowed_ids" in payload:
            assert payload["allowed_ids"] == expected
        if "essay_sources" in payload:
            assert [s["source_id"] for s in payload["essay_sources"]] == expected
        if "fixed_score" in payload:
            assert "evidence" not in payload  # no generated assessment prose
    for trait in ("ta", "cc", "lr", "gra"):
        evidence = getattr(result.criteria, trait).evidence
        assert [e.source_id for e in evidence] == ["P1S1", "P2S1", "P3S1", "P4S1"]
        assert evidence[-1].quote == "Same." and "đoạn 4" in evidence[-1].assessment
        assert all("Unverified" not in e.assessment for e in evidence)
    assert len([event for event, _ in events if event == "criterion.completed"]) == 4


async def test_task1_current_cache_key_includes_paragraph_provenance():
    from app.services.task1_input import TASK1_PROMPT_VERSION
    from app.services.writing_ai import input_fingerprint

    req, _ = await production_input("One.\nTwo.", task_number=1, require_essay=False)
    wrapped = req.model_copy(update={"paragraph_mode": "blank_lines"})
    assert input_fingerprint(req, TASK1_PROMPT_VERSION, "vllm", "model") != input_fingerprint(
        wrapped, TASK1_PROMPT_VERSION, "vllm", "model"
    )
