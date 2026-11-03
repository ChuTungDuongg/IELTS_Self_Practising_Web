"""Local operator policy, never a pricing-tier lookup or a resource selector."""

import re

from app.core.exceptions import AppError

BILLING_BLOCKED = "SPEAKING_AZURE_BILLING_NOT_AUTHORIZED"
QUOTA_EXCEEDED = "SPEAKING_AZURE_QUOTA_EXCEEDED"
AUTHENTICATION_FAILED = "SPEAKING_AZURE_AUTHENTICATION_FAILED"
TERMINAL_AZURE_ERRORS = frozenset({BILLING_BLOCKED, QUOTA_EXCEEDED, AUTHENTICATION_FAILED})


def billing_authorized(settings):
    mode = getattr(settings, "speaking_azure_billing_mode", "unknown")
    return mode == "free_only" or (
        mode == "paid" and getattr(settings, "speaking_azure_allow_paid", False) is True
    )


def require_billing_authorization(settings):
    if not billing_authorized(settings):
        raise AppError(BILLING_BLOCKED, "Speech resource billing is not authorized.", 409)


def quota_reason(value, *, sdk_code=None, too_many_requests=None):
    """Only structured codes/HTTP markers classify errors; raw details never leave here.

    SDK TooManyRequests alone does not distinguish monthly allowance, request rate or
    concurrency. Explicit provider subcodes refine telemetry without inventing a cause.
    """
    status = getattr(value, "status_code", None) or getattr(value, "http_status_code", None)
    details = getattr(value, "error_details", "")
    details = details[:4096] if isinstance(details, str) else ""
    if isinstance(value, Exception) and not details:
        details = str(value)[:4096]
    sdk_limited = too_many_requests is not None and sdk_code == too_many_requests
    http_limited = status in (429, "429") or bool(
        re.search(
            r"\b(?:http(?:\s+status)?|status(?:\s+code)?|httpstatus)\s*[:=]?\s*['\"]?429\b",
            details,
            re.IGNORECASE,
        )
    )
    if not sdk_limited and not http_limited:
        return None
    subcode = re.search(
        r"\b(?:errorcode|reasoncode)\s*[:=]\s*['\"]?"
        r"(RateLimitExceeded|ConcurrencyLimitExceeded|QuotaExhausted)\b",
        details,
        re.IGNORECASE,
    )
    if subcode:
        return {
            "ratelimitexceeded": "PROVIDER_RATE_LIMIT",
            "concurrencylimitexceeded": "PROVIDER_CONCURRENCY_LIMIT",
            "quotaexhausted": "PROVIDER_QUOTA_EXHAUSTED",
        }[subcode[1].lower()]
    return "SDK_TOO_MANY_REQUESTS" if sdk_limited else "HTTP_429"
