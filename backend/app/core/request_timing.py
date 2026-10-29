"""Optional, content-free ASGI request timing for controlled diagnostics."""

import logging
import re
import time

logger = logging.getLogger("uvicorn.error")
REQUEST_ID = re.compile(rb"^[0-9a-f]{32}$")
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


class RequestTimingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = next(
            (value for key, value in scope.get("headers", []) if key == b"x-request-id"), b""
        )
        request_id = request_id.decode("ascii") if REQUEST_ID.fullmatch(request_id) else "-"
        method = scope.get("method", "")
        method = method if method in METHODS else "OTHER"
        status = 0
        started = time.perf_counter()

        async def timed_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, timed_send)
        finally:
            logger.info(
                "api_timing id=%s method=%s status=%s total_ms=%.2f",
                request_id,
                method,
                status,
                (time.perf_counter() - started) * 1000,
            )
