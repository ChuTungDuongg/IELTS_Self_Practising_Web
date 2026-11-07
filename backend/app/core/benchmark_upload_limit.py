"""Bound request streaming before multipart files can exhaust temporary disk."""

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse


class BenchmarkUploadLimit:
    def __init__(self, app, *, max_bytes, prefix):
        self.app, self.maximum, self.path = (
            app,
            max_bytes + 65536,
            f"{prefix}/admin/speaking-benchmark/samples",
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != self.path:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        declared = headers.get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.maximum:
            return await JSONResponse(
                {
                    "code": "SPEAKING_BENCHMARK_UPLOAD_SIZE",
                    "message": "Recording exceeds the upload limit.",
                },
                status_code=413,
            )(scope, receive, send)
        consumed = 0
        exceeded = False
        response_headers = {}

        async def bounded_receive():
            nonlocal consumed, exceeded
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > self.maximum:
                exceeded = True
                # Starlette closes every partially spooled upload specifically on
                # MultiPartException. Preserve that cleanup path, then map the response.
                raise MultiPartException("SPEAKING_BENCHMARK_UPLOAD_SIZE")
            return message

        async def guarded_send(message):
            if not exceeded:
                await send(message)
            elif message["type"] == "http.response.start":
                response_headers.update(
                    {
                        key.decode("latin-1"): value.decode("latin-1")
                        for key, value in message.get("headers", [])
                        if key.lower() not in {b"content-length", b"content-type"}
                    }
                )

        try:
            await self.app(scope, bounded_receive, guarded_send)
        except MultiPartException:
            if not exceeded:
                raise
        if exceeded:
            await JSONResponse(
                {
                    "code": "SPEAKING_BENCHMARK_UPLOAD_SIZE",
                    "message": "Recording exceeds the upload limit.",
                },
                status_code=413,
                headers=response_headers,
            )(scope, receive, send)
