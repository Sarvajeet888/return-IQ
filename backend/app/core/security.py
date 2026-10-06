"""
Enterprise Security — JWT tokens, bcrypt passwords, API key hashing.
Uses bcrypt directly (no passlib) — compatible with bcrypt 4.x and 5.x.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.tracing import span
from app.core.config import get_settings

settings = get_settings()

API_KEY_PREFIX = "rl_live_"


# ── Password hashing (direct bcrypt — no passlib) ─────────────────────────────
def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt.

    PHASE 9 note: instrumented after tracing showed a registration request
    taking 330ms with only 1.35ms accounted for by queries. The remaining
    329ms is this function -- bcrypt at 12 rounds is *deliberately* slow, so
    this is correct behaviour, not a defect.

    It is worth making visible anyway. Without a span here, the next person
    investigating slow logins would reasonably suspect the database, since
    that is the only thing the trace showed. Naming expected cost is as
    useful as naming unexpected cost.
    """
    with span("auth.bcrypt_hash", rounds=12):
        pwd_bytes = plain.encode("utf-8")
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    with span("auth.bcrypt_verify"):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False


# ── JWT ───────────────────────────────────────────────────────────────────────
def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "type": "access", "jti": secrets.token_hex(16)}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str, jti: str | None = None) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). The jti is persisted server-side
    (see app/db/store.py refresh-token functions) so it can be rotated and
    revoked — plain JWTs alone can never be invalidated before they expire."""
    jti = jti or secrets.token_hex(16)
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": subject, "exp": expire, "type": "refresh", "jti": jti}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti, expire


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


# ── API Keys ──────────────────────────────────────────────────────────────────
def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key, prefix_for_display)."""
    raw_key = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    return raw_key, raw_key[:12]


def hash_api_key(raw_key: str, pepper: str) -> str:
    return hmac.new(
        key=pepper.encode("utf-8"),
        msg=raw_key.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_api_key(raw_key: str, pepper: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key, pepper), stored_hash)


# ── OTP ───────────────────────────────────────────────────────────────────────
def generate_otp(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))
