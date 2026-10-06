"""
Enterprise Settings - reads from environment variables with safe defaults for
demo mode, and hard failures in production for anything security-critical.

All values are resolved in __init__ (not as class-body defaults) so that
Settings() genuinely re-reads the environment every time it's instantiated -
class-body attributes only evaluate once, at import time, which would make
get_settings() lie about picking up env-var changes (e.g. in tests).
"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

_DEV_SECRET_FILE = Path(__file__).resolve().parent.parent.parent / ".dev_secret_key"
_DEV_PEPPER_FILE = Path(__file__).resolve().parent.parent.parent / ".dev_pepper"


def _persisted_dev_value(path: Path) -> str:
    """Generate a random value once and persist it to disk so local/demo
    restarts don't invalidate every previously-issued JWT and API key (the
    old behaviour: a fresh secrets.token_urlsafe(32) on every process start).
    This file is gitignored and is NOT used in production - see below.
    """
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_urlsafe(32)
    path.write_text(value)
    return value


_WEAK_SECRET_PLACEHOLDERS = {
    "change-me-in-production", "changeme", "change-me", "secret", "password",
    "dev", "development", "test", "example", "your-secret-key-here",
}


def _resolve_secret(env_name: str, dev_file: Path, environment: str) -> str:
    env_value = os.getenv(env_name)
    if env_value and env_value.strip().lower() not in _WEAK_SECRET_PLACEHOLDERS:
        return env_value
    if environment == "production":
        raise RuntimeError(
            f"{env_name} must be set explicitly to a real secret value in production. "
            f"Refusing to start with an unset, empty, or known-placeholder value "
            f"(e.g. a docker-compose '${{{env_name}:-change-me-in-production}}' fallback "
            f"that was never overridden)."
        )
    return env_value or _persisted_dev_value(dev_file)


class Settings:
    def __init__(self) -> None:
        # -- App --------------------------------------------------------------
        self.APP_NAME: str = "ReturnIQ - Enterprise Reverse Logistics Platform"
        self.APP_VERSION: str = "0.9.0-rc1"  # Phase 11: honest RC tag, not 1.0 - see phase11/release/VERSION_1.0.md
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

        # Demo mode - seeds a demo org/user/API key on first boot
        #
        # FINAL RELEASE: default flipped from "true" to "false".
        #
        # It previously defaulted ON, which meant a deployment that simply
        # forgot to set DEMO_MODE=false shipped a seeded organisation with a
        # KNOWN admin login (admin@sapnacollection.com / Demo@12345, role
        # org_admin) plus demo API-key and password-reset-token endpoints,
        # live and reachable. A missing env var is not an acceptable
        # distance between "deployed" and "publicly known admin password".
        #
        # Defaults must fail safe. Anyone who genuinely wants the demo seed
        # can ask for it explicitly; nobody should get it by omission.
        self.DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"

        # Belt-and-braces: even an explicit DEMO_MODE=true is refused in
        # production. The env var is set by hand, and a hand-set value is
        # exactly what gets copied between environments by accident.
        if self.DEMO_MODE and self.ENVIRONMENT == "production":
            raise RuntimeError(
                "DEMO_MODE=true is refused when ENVIRONMENT=production. The "
                "demo seed creates an organisation with a publicly known "
                "admin password and exposes demo credential endpoints. If "
                "this is genuinely a demo deployment, set "
                "ENVIRONMENT=staging."
            )

        # DEBUG must never be on in production: it changes error responses to
        # include stack traces, which leak file paths, dependency versions
        # and query fragments to anyone who can trigger a 500.
        if self.DEBUG and self.ENVIRONMENT == "production":
            raise RuntimeError(
                "DEBUG=true is refused when ENVIRONMENT=production. Debug "
                "responses expose stack traces and internal paths to any "
                "caller who can trigger an error."
            )

        # -- Database -----------------------------------------------------------
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "")
        self.DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "20"))
        self.DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
        self.DB_POOL_TIMEOUT_SECONDS: int = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))
        self.DB_ECHO_SQL: bool = os.getenv("DB_ECHO_SQL", "false").lower() == "true"

        # -- Redis (rate limiting + future caching) ------------------------------
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.USE_REDIS_RATE_LIMIT: bool = os.getenv("USE_REDIS_RATE_LIMIT", "false").lower() == "true"

        # -- Security -------------------------------------------------------------
        # SECRET_KEY / API_KEY_HASH_PEPPER: MUST be set via env in production.
        # In dev/demo they're generated once and persisted locally so restarting
        # the server doesn't silently invalidate every issued token.
        self.SECRET_KEY: str = _resolve_secret("SECRET_KEY", _DEV_SECRET_FILE, self.ENVIRONMENT)
        self.API_KEY_HASH_PEPPER: str = _resolve_secret("API_KEY_HASH_PEPPER", _DEV_PEPPER_FILE, self.ENVIRONMENT)

        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
        self.REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
        self.ALGORITHM: str = "HS256"
        self.BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", "12"))
        self.MAX_LOGIN_ATTEMPTS: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
        self.LOCKOUT_DURATION_MINUTES: int = int(os.getenv("LOCKOUT_DURATION_MINUTES", "15"))

        # Refresh token cookie
        self.REFRESH_COOKIE_NAME: str = "rl_refresh_token"
        self.COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
        self.COOKIE_SAMESITE: str = os.getenv("COOKIE_SAMESITE", "lax")

        # -- CORS -------------------------------------------------------------------
        self.CORS_ORIGINS: list = [
            o.strip() for o in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
            ).split(",") if o.strip()
        ]

        # -- Rate Limiting -------------------------------------------------------
        self.RATE_LIMIT_DEFAULT: str = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
        self.RATE_LIMIT_LOGIN: str = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
        self.RATE_LIMIT_REGISTER: str = os.getenv("RATE_LIMIT_REGISTER", "5/minute")

        # -- ML / AI ----------------------------------------------------------------
        self.ML_ARTIFACTS_PATH: str = os.getenv("ML_ARTIFACTS_PATH", "ml/artifacts")
        self.DEFAULT_RISK_THRESHOLD: float = float(os.getenv("DEFAULT_RISK_THRESHOLD", "50.0"))
        self.FRAUD_SCORE_THRESHOLD: float = float(os.getenv("FRAUD_SCORE_THRESHOLD", "75.0"))

        # -- Email --------------------------------------------------------------------
        self.SMTP_HOST: str = os.getenv("SMTP_HOST", "")
        self.SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_USER: str = os.getenv("SMTP_USER", "")
        self.SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
        # Sender address. Email sending is disabled unless both SMTP_HOST and
        # SMTP_FROM are set - see services/email_service.is_configured().
        self.SMTP_FROM: str = os.getenv("SMTP_FROM", "")
        # Public URL of the frontend, used to build links inside emails.
        # Falls back to the first CORS origin, which is correct in almost
        # every deployment and avoids a second thing to configure.
        self.APP_BASE_URL: str = os.getenv("APP_BASE_URL", "")

        # ── File storage (Phase 12) ──────────────────────────────────────
        # S3 is used when AWS_S3_BUCKET is set; otherwise local disk.
        self.AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "")
        self.AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")
        self.AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
        self.AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        self.LOCAL_UPLOAD_DIR: str = os.getenv("LOCAL_UPLOAD_DIR", "/app/uploads")

        # ── PII encryption (Phase 12) ────────────────────────────────────
        # Optional. If unset, the key is derived from SECRET_KEY via HKDF.
        # Set explicitly if you need to rotate JWT signing independently of
        # data encryption - rotating SECRET_KEY otherwise makes stored PII
        # unreadable.
        self.PII_ENCRYPTION_KEY: str = os.getenv("PII_ENCRYPTION_KEY", "")
        self.FROM_EMAIL: str = os.getenv("FROM_EMAIL", "noreply@returniq.io")

        # -- Storage ------------------------------------------------------------------
        self.S3_BUCKET: str = os.getenv("S3_BUCKET", "")
        self.AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")
        self.AWS_ACCESS_KEY: str = os.getenv("AWS_ACCESS_KEY", "")
        self.AWS_SECRET_KEY: str = os.getenv("AWS_SECRET_KEY", "")

        # -- Pagination ----------------------------------------------------------------
        self.DEFAULT_PAGE_SIZE: int = 20
        self.MAX_PAGE_SIZE: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
