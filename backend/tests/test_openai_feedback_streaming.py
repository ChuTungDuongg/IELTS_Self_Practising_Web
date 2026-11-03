"""Real Chat SSE transport with fictional chunks, no paid inference."""

import asyncio
import json

import httpx
import pytest
from test_openai_integration import intercept, settings

from app.providers.writing_llm.base import CompletionOptions, ProviderFailure
from app.providers.writing_llm.openai import OpenAIProvider


def event(content=None, *, finish=None, usage=None, refusal=None):
    data = {
        "choices": [
            {"index": 0, "delta": {"content": content, "refusal": refusal}, "finish_reason": finish}
        ]
    }
    if usage is not None:
        data = {"choices": [], "usage": usage}
    return ("data: " + json.dumps(data) + "\n\n").encode()


async def test_feedback_tokens_arrive_before_completion_and_usage_is_counted_once(monkeypatch):
    partial = asyncio.Event()
    release = asyncio.Event()
    seen = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield event('{"observations":[{"observation":"Nhận xét')
            await release.wait()
            yield event(' trực tiếp."}]}')
            yield event(finish="stop")
            yield event(
                usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 8,
                    "total_tokens": 18,
                    "completion_tokens_details": {"reasoning_tokens": 3},
                }
            )
            yield b"data: [DONE]\n\n"

    def handler(request):
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        assert body["reasoning_effort"] == "low"
        assert body["max_completion_tokens"] == 8192
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Stream())

    async def preview(text):
        seen.append(text)
        if text:
            partial.set()

    intercept(monkeypatch, handler)
    job = asyncio.create_task(
        OpenAIProvider(settings()).complete(
            [],
            {},
            options=CompletionOptions(
                task="task2", stage="feedback", criterion="cc", on_content=preview
            ),
        )
    )
    try:
        await asyncio.wait_for(partial.wait(), 1)
        assert not job.done()
        release.set()
        result = await job
        assert seen[0] is None
        assert json.loads(result.text)["observations"][0]["observation"] == "Nhận xét trực tiếp."
        assert result.usage == {
            "prompt_tokens": 10,
            "completion_tokens": 8,
            "total_tokens": 18,
            "reasoning_tokens": 3,
        }
        assert len(result.attempts) == 1
    finally:
        release.set()
        await asyncio.gather(job, return_exceptions=True)


@pytest.mark.parametrize(
    "finish,done,refusal",
    [("stop", False, None), ("content_filter", True, None), ("stop", True, "private refusal")],
)
async def test_incomplete_filtered_or_refused_stream_is_never_accepted(
    monkeypatch, finish, done, refusal
):
    calls = []

    def handler(request):
        calls.append(request)
        content = event('{"feedback":"draft"}', refusal=refusal) + event(finish=finish)
        content += event(usage={"completion_tokens": 9})
        if done:
            content += b"data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=content)

    async def preview(_text):
        pass

    intercept(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as error:
        await OpenAIProvider(settings()).complete(
            [], {}, options=CompletionOptions(stage="feedback", on_content=preview)
        )
    assert len(calls) == 1
    assert error.value.usage["completion_tokens"] == 9


async def test_feedback_preview_extracts_only_business_text_and_decodes_split_escapes():
    from app.services.writing_feedback_stream import FeedbackPreviewText

    parser = FeedbackPreviewText()
    raw = json.dumps(
        {
            "score": 9,
            "reasoning_content": "PRIVATE",
            "source_id": "P1S1",
            "observations": [{"observation": 'Nhận xét "đúng" 😀'}, {"observation": "Dòng\nhai"}],
        },
        ensure_ascii=True,
    )
    snapshots = [parser.feed(char) for char in raw]
    assert "Nhận" in snapshots
    assert snapshots[-1] == 'Nhận xét "đúng" 😀\n\nDòng\nhai'
    assert all("PRIVATE" not in text and "P1S1" not in text for text in snapshots)


async def test_length_repair_resets_draft_and_preserves_both_attempts_usage(monkeypatch):
    calls, previews = [], []

    def handler(request):
        calls.append(json.loads(request.content))
        finish = "length" if len(calls) == 1 else "stop"
        payload = event('{"feedback":"draft"}') + event(finish=finish)
        payload += event(usage={"completion_tokens": len(calls) * 10})
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=payload + b"data: [DONE]\n\n",
        )

    async def preview(text):
        previews.append(text)

    intercept(monkeypatch, handler)
    result = await OpenAIProvider(settings()).complete(
        [], {}, options=CompletionOptions(stage="feedback", on_content=preview)
    )
    assert [body["max_completion_tokens"] for body in calls] == [8192, 32768]
    assert previews == [None, '{"feedback":"draft"}', None, '{"feedback":"draft"}']
    assert result.usage == {"completion_tokens": 30}
    assert len(result.attempts) == 2


async def test_cancelled_stream_keeps_known_usage_and_never_replays_post(monkeypatch):
    received = asyncio.Event()
    calls = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield event(
                usage={
                    "completion_tokens": 12,
                    "completion_tokens_details": {"reasoning_tokens": 4},
                }
            )
            received.set()
            await asyncio.Event().wait()

    def handler(request):
        calls.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Stream())

    async def preview(_text):
        pass

    intercept(monkeypatch, handler)
    job = asyncio.create_task(
        OpenAIProvider(settings()).complete(
            [], {}, options=CompletionOptions(stage="feedback", on_content=preview)
        )
    )
    await asyncio.wait_for(received.wait(), 1)
    job.cancel()
    with pytest.raises(asyncio.CancelledError) as error:
        await job
    assert len(calls) == 1
    assert error.value.usage == {"completion_tokens": 12, "reasoning_tokens": 4}


async def test_preview_reset_and_flush_are_separate_from_validated_results():
    from app.services.writing_feedback_stream import FeedbackPreview

    events = []

    async def trace(kind, payload):
        events.append((kind, payload))

    preview = FeedbackPreview("lr", trace)
    await preview.feed(None)
    await preview.feed('{"observations":[{"observation":"A provisional')
    await preview.feed(' comment."}]}')
    await preview.flush()
    assert events[-1][1].feedback_preview == "A provisional comment."
    assert all(
        kind == "criterion.feedback.draft" and payload.result is None for kind, payload in events
    )
    await preview.feed(None)
    assert events[-1][1].feedback_preview == ""


async def test_non_feedback_options_never_enable_streaming_even_with_a_callback(monkeypatch):
    from test_openai_integration import completed

    def handler(request):
        assert json.loads(request.content)["stream"] is False
        return completed()

    async def preview(_text):
        pytest.fail("Score stage must not produce preview tokens")

    intercept(monkeypatch, handler)
    await OpenAIProvider(settings()).complete(
        [], {}, options=CompletionOptions(stage="scoring", on_content=preview)
    )
