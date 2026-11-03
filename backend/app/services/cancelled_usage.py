"""One metadata-only handoff after an explicit, durable worker cancellation.

The normal lease is revoked immediately. A hash of that former lease authorizes
one final usage checkpoint only; it cannot authorize scores, lifecycle updates,
events or a different execution. Callers hold the run row lock throughout.
"""

import hashlib
import hmac
from uuid import UUID

_FENCE = "cancelled_usage_fence"


def _lease_hash(token: object) -> str | None:
    if not isinstance(token, (str, UUID)) or not 0 < len(str(token)) <= 128:
        return None
    return hashlib.sha256(str(token).encode()).hexdigest()


def arm_cancelled_usage(usage: dict | None, token: object) -> dict:
    """Replace old authority, including clearing it when cancelling a queued run."""
    result = {key: value for key, value in (usage or {}).items() if key != _FENCE}
    digest = _lease_hash(token)
    if digest is not None:
        result[_FENCE] = {"lease_sha256": digest, "consumed": False}
    return result


def consume_cancelled_usage(usage: dict | None, token: object) -> dict | None:
    """Return a consumed copy; applying it is atomic with the final usage write."""
    digest = _lease_hash(token)
    fence = (usage or {}).get(_FENCE)
    if not isinstance(fence, dict) or digest is None or fence.get("consumed") is not False:
        return None
    previous_hash = fence.get("lease_sha256")
    if (
        not isinstance(previous_hash, str)
        or len(previous_hash) != 64
        or not previous_hash.isascii()
        or not hmac.compare_digest(previous_hash, digest)
    ):
        return None
    return {**(usage or {}), _FENCE: {"lease_sha256": digest, "consumed": True}}
