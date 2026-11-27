"""Password hashing and stateless access tokens using only the standard library.

Tokens are HMAC-SHA256 signed JSON payloads. Secrets always come from configuration,
never from source code in deployments.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import settings

_PBKDF2_ROUNDS = 210_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(subject: str, claims: dict | None = None) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + settings.access_token_expire_minutes * 60,
        # Unique per issue: two logins in the same second must never produce the
        # same token, otherwise revoking one would silently revoke the other.
        "jti": secrets.token_hex(16),
    }
    if claims:
        payload.update(claims)
    header = _b64url(b'{"alg":"HS256","typ":"JWT"}')
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}".encode()
    signature = hmac.new(settings.secret_key.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(signature)}"


def decode_access_token(token: str) -> dict | None:
    import time

    try:
        header, body, signature = token.split(".")
        header_data = json.loads(_unb64url(header))
        # Pin the algorithm: accepting attacker-supplied "alg" values would let
        # a token be forged with a different verification scheme.
        if header_data.get("alg") != "HS256" or header_data.get("typ", "JWT") != "JWT":
            return None
        expected = hmac.new(
            settings.secret_key.encode(), f"{header}.{body}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _unb64url(signature)):
            return None
        payload = json.loads(_unb64url(body))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def token_digest(token: str) -> str:
    """Key the persistent revocation record without retaining a raw token."""
    return hmac.new(settings.secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()
