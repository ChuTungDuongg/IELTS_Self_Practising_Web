from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.exceptions import AppError

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_LENGTH = 32


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise AppError("PASSWORD_TOO_SHORT", "Password must be at least 8 characters.", 422)
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_LENGTH,
    )
    return "$".join(
        (
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _b64encode(salt),
            _b64encode(derived),
        )
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_hash = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        n, r, p = int(raw_n), int(raw_r), int(raw_p)
        if n > 2**18 or r > 32 or p > 8:
            return False
        expected = _b64decode(raw_hash)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(raw_salt),
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: UUID
    token_type: str
    expires_at: datetime
    jwt_id: str | None
    role: str | None


def create_token(
    *,
    subject: UUID,
    token_type: str,
    secret: str,
    issuer: str,
    audience: str,
    lifetime: timedelta,
    role: str | None = None,
    jwt_id: str | None = None,
    now: datetime | None = None,
) -> str:
    issued_at = (now or datetime.now(UTC)).astimezone(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iss": issuer,
        "aud": audience,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + lifetime).timestamp()),
    }
    if role is not None:
        payload["role"] = role
    if jwt_id is not None:
        payload["jti"] = jwt_id
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_json_segment(header)}.{_json_segment(payload)}"
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256)
    return f"{signing_input}.{_b64encode(signature.digest())}"


def decode_token(
    token: str,
    *,
    expected_type: str,
    secret: str,
    issuer: str,
    audience: str,
    now: datetime | None = None,
) -> TokenClaims:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        signing_input = f"{encoded_header}.{encoded_payload}"
        expected_signature = hmac.new(
            secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected_signature, _b64decode(encoded_signature)):
            raise ValueError("signature")
        header = json.loads(_b64decode(encoded_header))
        payload = json.loads(_b64decode(encoded_payload))
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise ValueError("algorithm")
        if payload.get("iss") != issuer or payload.get("aud") != audience:
            raise ValueError("claims")
        if payload.get("type") != expected_type:
            raise ValueError("type")
        current = int((now or datetime.now(UTC)).timestamp())
        if not isinstance(payload.get("exp"), int) or payload["exp"] <= current:
            raise AppError("TOKEN_EXPIRED", "The authentication token has expired.", 401)
        return TokenClaims(
            subject=UUID(payload["sub"]),
            token_type=payload["type"],
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
            jwt_id=payload.get("jti"),
            role=payload.get("role"),
        )
    except AppError:
        raise
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise AppError("INVALID_TOKEN", "The authentication token is invalid.", 401) from exc


def token_fingerprint(jwt_id: str) -> str:
    return hashlib.sha256(jwt_id.encode("utf-8")).hexdigest()


def _json_segment(value: dict[str, Any]) -> str:
    return _b64encode(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
