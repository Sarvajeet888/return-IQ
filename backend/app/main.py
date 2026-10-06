"""ReturnIQ Enterprise - FastAPI Application Entry Point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from app.core.logging_config import configure_logging
from app.core.metrics import register_metrics

# Configure structured JSON logging before anything else
configure_logging()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.routes import (
    admin,
    ai_ux,
    insights,
    auth,
    cod_risk,
    customers,
    misc,
    notifications,
    portal,
    org_mgmt,
    orgs,
    remittance,
    reports,
    return_mgmt,
    returns,
    users,
    workflows,
)
from app.core.config import get_settings
from app.core.logging_config import RequestIdMiddleware, configure_logging
from app.core.rate_limit import limiter

settings = get_settings()
logger = logging.getLogger("app")


# PHASE 7 — Content Security Policy.
#
# This API serves JSON, not HTML, so the strictest possible policy is also the
# correct one: nothing should ever be loaded or executed from a response here.
# `default-src 'none'` denies every fetch directive by default rather than
# enumerating what to block and inevitably missing one.
#
# `frame-ancestors 'none'` duplicates X-Frame-Options: DENY on purpose. CSP is
# the standard modern browsers actually follow, X-Frame-Options is the one
# older ones understand, and clickjacking protection is worth two lines.
#
# NOTE: this policy is for the API. The React frontend is served by nginx and
# needs its own, looser policy (it must load its own scripts and styles).
# Applying this one there would break the app -- that is deliberately a
# separate config, not an oversight.
_CSP: bytes = (
    b"default-src 'none'; "
    b"frame-ancestors 'none'; "
    b"base-uri 'none'; "
    b"form-action 'none'"
)


class SecurityHeadersMiddleware:
    """Adds baseline security response headers to every response.
    Previously absent entirely - no clickjacking protection, no MIME-sniffing
    protection, no HSTS. These are cheap, standard defense-in-depth headers
    that OWASP's Security Misconfiguration category expects by default."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                headers.append((b"permissions-policy", b"geolocation=(), camera=(), microphone=()"))
                headers.append((b"content-security-policy", _CSP))
                # Isolate the browsing context so a compromised third-party
                # tab cannot reference this window, and block cross-origin
                # reads of API responses.
                headers.append((b"cross-origin-opener-policy", b"same-origin"))
                headers.append((b"cross-origin-resource-policy", b"same-origin"))
                if settings.ENVIRONMENT == "production":
                    headers.append((b"strict-transport-security", b"max-age=63072000; includeSubDomains"))
            await send(message)

        await self.app(scope, receive, send_wrapper)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    from app.services.ml_service import get_predictor
    logger.info("Loading ML model...")
    get_predictor()
    logger.info("ML model loaded.")

    from app.db import store
    creds = store.get_demo_credentials()
    if settings.DEMO_MODE and creds:
        logger.info(
            "DEMO MODE active | email=admin@sapnacollection.com password=Demo@12345 "
            "api_key_prefix=%s | docs=/docs",
            (creds.get("api_key") or "")[:20],
        )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Enterprise Reverse Logistics AI Platform",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(RequestIdMiddleware)   # Phase 8.7 — structured JSON logging + correlation IDs
    app.add_middleware(SecurityHeadersMiddleware)
    register_metrics(app)   # Phase 8.6 — Prometheus /metrics endpoint
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # PHASE 31: the only unauthenticated routes that touch customer data.
    # Registered explicitly rather than mounted under the authenticated
    # prefix, so nobody adds an endpoint here by accident.
    app.include_router(portal.router)
    app.include_router(insights.router)
    app.include_router(auth.router)
    app.include_router(returns.router)
    app.include_router(orgs.router)
    app.include_router(misc.router)
    # Phase 5 routers
    app.include_router(users.router)
    app.include_router(org_mgmt.router)
    app.include_router(return_mgmt.router)
    app.include_router(customers.router)
    app.include_router(notifications.router)
    app.include_router(reports.router)
    app.include_router(admin.router)
    app.include_router(workflows.router)
    app.include_router(ai_ux.router)
    # Merged from the parallel feature branch
    app.include_router(cod_risk.router)
    app.include_router(remittance.router)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log the full exception server-side (with request_id + traceback)
        # but never leak internals to the client - the old handler returned
        # f"Internal error: {str(exc)}" straight to the caller, which is an
        # information-disclosure bug (stack details, DB errors, file paths).
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        content = {"detail": "Internal server error. Please try again or contact support."}
        if settings.DEBUG:
            content["debug_detail"] = str(exc)
        return JSONResponse(status_code=500, content=content)

    return app


app = create_app()
