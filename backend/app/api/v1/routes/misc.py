"""Customers, Warehouses, AI stats, Health routes."""
from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_org
from app.core.config import get_settings
from app.db import store
from app.services.ml_service import get_model_stats

settings = get_settings()
router = APIRouter(tags=["misc"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "demo_mode": settings.DEMO_MODE,
    }


# ── Phase 8.6: Kubernetes / ECS style probes ─────────────────────────────────

@router.get("/health/live", tags=["health"])
async def liveness() -> dict:
    """
    Liveness probe — is the process alive?
    Deliberately does NOT check the database. If the DB is down, the app is
    still 'live' and should not be killed and restarted (a restart won't fix
    a dead database, and a restart loop makes recovery harder).
    """
    return {"status": "alive"}


@router.get("/health/ready", tags=["health"])
async def readiness() -> dict:
    """
    Readiness probe — can this instance serve traffic?
    Checks the database and (if enabled) Redis. A load balancer should stop
    routing traffic here if this fails, but should NOT restart the container.
    """
    from fastapi import HTTPException
    checks = {}
    healthy = True

    # Database check
    try:
        from sqlalchemy import text

        from app.db.database import SessionLocal
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
        healthy = False

    # ML model check — the core feature doesn't work without it
    try:
        stats = get_model_stats()
        checks["ml_model"] = "ok" if stats else "unavailable"
        if not stats:
            healthy = False
    except Exception as exc:
        checks["ml_model"] = f"error: {type(exc).__name__}"
        healthy = False

    # Redis check (only if rate limiting depends on it)
    if getattr(settings, "USE_REDIS_RATE_LIMIT", False):
        try:
            from app.core.cache import get_redis
            r = get_redis()
            if r is not None:
                r.ping()
                checks["redis"] = "ok"
            else:
                checks["redis"] = "unavailable"
                # Redis down means rate limiting is degraded but the app
                # still works — don't fail readiness for this.
        except Exception as exc:
            checks["redis"] = f"error: {type(exc).__name__}"

    if not healthy:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})

    return {"status": "ready", "checks": checks}


# backward compat alias (v2 used /api/v1/merchants/demo-key)
@router.get("/api/v1/merchants/demo-key", tags=["setup"])
async def legacy_demo_key() -> dict:
    if not settings.DEMO_MODE:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not available in production")
    creds = store.get_demo_credentials()
    return {
        "demo_api_key": (creds or {}).get("api_key", ""),
        "demo_credentials": {"email": "admin@sapnacollection.com", "password": "Demo@12345"},
        "note": "Demo mode. Use these credentials to log in.",
    }


# ── Legacy customer routes removed (Phase 9) ────────────────────────────────
# GET /api/v1/customers and GET /api/v1/customers/{customer_id} used to be
# defined here. Phase 5 added a full customers router (routes/customers.py)
# on the same paths, but because misc.router is registered BEFORE
# customers.router in main.py, FastAPI matched these simpler handlers first -
# silently shadowing the Phase 5 endpoints. The richer versions (pagination,
# search, risk/blacklist filters, per-customer analytics) were unreachable
# dead code, and FastAPI emitted a duplicate-operation-id warning that also
# corrupts the generated OpenAPI spec and any client SDK built from it.
# Removed here so routes/customers.py is the single owner of these paths.

@router.get("/api/v1/warehouses")
async def list_warehouses(org: dict = Depends(get_current_org)) -> list:
    return store.get_warehouses_for_org(org["id"])


@router.get("/api/v1/ai/models")
async def ai_model_stats(org: dict = Depends(get_current_org)) -> dict:
    return get_model_stats()


@router.get("/api/v1/ai/insights")
async def ai_insights(org: dict = Depends(get_current_org)) -> dict:
    stats = store.get_dashboard_stats(org["id"])
    total = stats["total_returns"]
    return {
        "summary": f"Analyzed {total} returns. AI auto-approved {stats['decisions'].get('accept', 0)} and blocked {stats['decisions'].get('reject', 0)} high-risk requests.",
        "top_recommendations": [
            {"title": "Reduce COD Returns", "impact": "high", "description": "COD returns have 2.3x higher fraud rate. Consider offering prepaid incentives."},
            {"title": "Festive Season Surge", "impact": "medium", "description": "Returns spike 40% during festive season. Pre-position warehouse staff."},
            {"title": "Apparel Size Issues", "impact": "high", "description": "28% of apparel returns cite size issues. Add size guide to product pages."},
            {"title": "BlueDart Optimization", "impact": "low", "description": "BlueDart routes have 12% higher return shipping cost vs Delhivery for metro routes."},
        ],
        "model_health": get_model_stats(),
        "carbon_insights": {
            "total_kg": stats.get("total_carbon_kg", 0),
            "equivalent_trees": round(stats.get("total_carbon_kg", 0) / 21.77, 1),
            "recommendation": "Switching to Delhivery for short-haul returns (<200km) could reduce carbon footprint by ~18%."
        }
    }
