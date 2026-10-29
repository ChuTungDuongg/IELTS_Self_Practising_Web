import logging

import pytest

from app.core.request_timing import RequestTimingMiddleware


@pytest.mark.asyncio
async def test_streaming_passes_through_and_timing_log_excludes_private_data(caplog):
    messages = []

    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        await send({"type": "http.response.body", "body": b"second", "more_body": False})

    async def send(message):
        messages.append(message)

    async def receive():
        return {"type": "http.request", "body": b"private body"}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/secret",
        "query_string": b"token=secret",
        "headers": [(b"authorization", b"secret"), (b"x-request-id", b"a" * 32)],
    }
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        await RequestTimingMiddleware(application)(scope, receive, send)
    assert [message.get("body") for message in messages[1:]] == [b"first", b"second"]
    assert messages[1]["more_body"] is True
    assert "id=" + "a" * 32 in caplog.text
    assert "status=200" in caplog.text
    assert "secret" not in caplog.text
    assert "private body" not in caplog.text


@pytest.mark.asyncio
async def test_untrusted_request_id_is_never_logged(caplog):
    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})

    async def send(_message):
        pass

    async def receive():
        return {"type": "http.request"}

    scope = {
        "type": "http",
        "method": "GET",
        "headers": [(b"x-request-id", b"private-token")],
    }
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        await RequestTimingMiddleware(application)(scope, receive, send)
    assert "id=-" in caplog.text
    assert "private-token" not in caplog.text
