"""Setup client: no redirects, environmental proxies, request bodies or cookies in errors."""

import httpx
from benchmarks.load.safety import SafetyError, validate_manifest, validate_path


class RequestFailure(ValueError):
    pass


class GuardedClient:
    def __init__(self, manifest, token, *, transport=None):
        validate_manifest(manifest, requested_users=1)
        self.client = httpx.AsyncClient(
            base_url=manifest["base_url"],
            headers={"X-Load-Token": token},
            timeout=30,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self.client.__aexit__(*args)

    async def request(self, method, path, *, name, expected=(200,), **kwargs):
        try:
            validate_path(path)
        except SafetyError:
            raise RequestFailure("TARGET_PATH_INVALID") from None
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise RequestFailure(f"{name}: TRANSPORT_FAILURE") from None
        if response.status_code not in expected:
            raise RequestFailure(f"{name}: HTTP_{response.status_code}")
        return response.json() if response.content else None
