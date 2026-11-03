"""Local CPU startup verification. Requires an explicitly selected, empty test database."""

import asyncio
import json
import os
import sys
from urllib.parse import urlsplit


async def main():
    database = urlsplit(os.environ.get("DATABASE_URL", "")).path
    if not database.endswith("/ielts_hybrid_cpu_test"):
        raise RuntimeError("SPEAKING_CPU_PROBE_REQUIRES_DEDICATED_TEST_DATABASE")
    import httpx

    from app.main import app, settings
    from app.services.speaking_profile import hybrid_profile_status

    assert settings.speaking_profile == "speaking_hybrid_v1"
    assert not settings.speaking_asr_enabled and not settings.speaking_ai_enabled
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://probe") as client:
            assert (await client.get("/api/v1/health")).status_code == 200
            assert (await client.get("/api/v1/ready")).status_code == 200
        assert not any(name in sys.modules for name in ("torch", "faster_whisper", "ctranslate2"))
        status = hybrid_profile_status(settings)
        assert not status["configured"]  # Missing credentials do not become a ready speech profile.
    print(json.dumps({"status": "CPU_BACKEND_STARTUP_OK", "provider_calls": 0, "gpu_required": False}))


if __name__ == "__main__":
    asyncio.run(main())
