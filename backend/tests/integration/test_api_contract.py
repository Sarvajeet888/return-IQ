"""
API contract & validation tests (Phase 9.6).

Verifies the API behaves as documented in docs/guides/API_GUIDE.md:
  - OpenAPI spec is generated and matches the routes
  - Error codes are correct and consistent
  - Pagination works and is bounded
  - Input validation rejects bad data
  - Auth is enforced on every protected route
"""
from __future__ import annotations
import uuid

import pytest


def _org(client, label="api"):
    r = client.post("/api/v1/auth/register", json={
        "full_name": "API Test", "email": f"{label}_{uuid.uuid4().hex[:8]}@example.com",
        "password": "TestPass123", "org_name": f"Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200
    return r.json()["access_token"]


# ── OpenAPI spec ─────────────────────────────────────────────────────────────

def test_openapi_spec_is_generated(app_client):
    r = app_client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["openapi"].startswith("3.")
    assert "paths" in spec
    assert len(spec["paths"]) > 30, f"only {len(spec['paths'])} paths - routes may be unregistered"


def test_openapi_documents_all_major_route_groups(app_client):
    spec = app_client.get("/openapi.json").json()
    paths = " ".join(spec["paths"].keys())

    for group in ["/auth/", "/returns", "/customers", "/reports/",
                  "/workflows/", "/admin/", "/ai/", "/notifications/", "/users/", "/org/"]:
        assert group in paths, f"route group {group} missing from OpenAPI spec"


def test_openapi_has_no_duplicate_operation_ids(app_client):
    """Duplicate operationIds break generated client SDKs."""
    spec = app_client.get("/openapi.json").json()
    ids = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if isinstance(op, dict) and "operationId" in op:
                ids.append(op["operationId"])
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate operationIds: {dupes}"


# ── Health & probe endpoints ─────────────────────────────────────────────────

def test_health_endpoint_shape(app_client):
    r = app_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    for field in ["status", "app", "version", "environment"]:
        assert field in body, f"health response missing {field}"


def test_liveness_probe_does_not_require_auth(app_client):
    r = app_client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


def test_readiness_probe_reports_dependency_checks(app_client):
    r = app_client.get("/health/ready")
    # 200 = ready, 503 = degraded. Both are valid responses; 500 is not.
    assert r.status_code in (200, 503)
    body = r.json() if r.status_code == 200 else r.json().get("detail", {})
    assert "checks" in body
    assert "database" in body["checks"]


# ── Authentication enforcement ───────────────────────────────────────────────

PROTECTED_ENDPOINTS = [
    ("GET",  "/api/v1/returns"),
    ("GET",  "/api/v1/returns/dashboard"),
    ("GET",  "/api/v1/customers/"),
    ("GET",  "/api/v1/notifications/"),
    ("GET",  "/api/v1/reports/summary"),
    ("GET",  "/api/v1/workflows/rules"),
    ("GET",  "/api/v1/ai/performance"),
    ("GET",  "/api/v1/users/profile"),
    ("GET",  "/api/v1/org/feature-flags"),
    ("GET",  "/api/v1/admin/health"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_protected_endpoints_require_auth(app_client, method, path):
    r = app_client.request(method, path)
    assert r.status_code in (401, 403), (
        f"UNAUTHENTICATED ACCESS: {method} {path} returned {r.status_code}"
    )


# ── Input validation ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("field,bad_value", [
    ("item_value", -100.0),           # negative money
    ("weight_grams", -50),            # negative weight
    ("origin_pincode", "12"),         # too short
    ("origin_pincode", "ABCDEF"),     # non-numeric
    ("payment_mode", "Bitcoin"),      # not a payment mode the app supports
])
def test_invalid_return_fields_rejected(app_client, field, bad_value):
    token = _org(app_client, "validate")
    payload = {
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "test@example.com",
        "sku": "SKU-1", "item_category": "Electronics", "item_value": 1000.0,
        "origin_pincode": "400001", "destination_pincode": "560001",
        "weight_grams": 1000, "volumetric_weight_grams": 1200,
        "return_reason_code": "defective", "courier": "BlueDart",
        "payment_mode": "Prepaid", "fragile": False, "festive": False,
        "condition": "good",
    }
    payload[field] = bad_value

    r = app_client.post("/api/v1/returns",
                        headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert r.status_code == 422, f"invalid {field}={bad_value!r} was accepted"


def test_missing_required_field_rejected(app_client):
    token = _org(app_client, "missing")
    r = app_client.post("/api/v1/returns",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"sku": "only-one-field"})
    assert r.status_code == 422


def test_malformed_json_rejected(app_client):
    token = _org(app_client, "malformed")
    r = app_client.post("/api/v1/returns",
                        headers={"Authorization": f"Bearer {token}",
                                 "Content-Type": "application/json"},
                        content=b"{not valid json")
    assert r.status_code == 422


def test_invalid_email_format_rejected_at_registration(app_client):
    for bad_email in ["notanemail", "@example.com", "user@", "user @example.com"]:
        r = app_client.post("/api/v1/auth/register", json={
            "full_name": "Test", "email": bad_email, "password": "TestPass123",
            "org_name": "Org", "platform_type": "shopify", "accepted_terms": True,
        })
        assert r.status_code == 422, f"invalid email {bad_email!r} accepted"


# ── Pagination ───────────────────────────────────────────────────────────────

def test_pagination_returns_expected_shape(app_client):
    token = _org(app_client, "paginate")
    r = app_client.get("/api/v1/returns?page=1&page_size=10",
                       headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    for field in ["items", "total", "page", "page_size"]:
        assert field in body, f"pagination response missing {field}"


def test_page_size_upper_bound_enforced(app_client):
    """
    An unbounded page_size is a DoS vector - a single request could pull
    every row in the table.
    """
    token = _org(app_client, "pagesize")
    r = app_client.get("/api/v1/returns?page=1&page_size=100000",
                       headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422, "unbounded page_size accepted - DoS risk"


def test_negative_page_rejected(app_client):
    token = _org(app_client, "negpage")
    r = app_client.get("/api/v1/returns?page=-1",
                       headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


def test_customers_pagination_bounded(app_client):
    token = _org(app_client, "custpage")
    r = app_client.get("/api/v1/customers/?page=1&page_size=99999",
                       headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


# ── Error code correctness ───────────────────────────────────────────────────

def test_nonexistent_resource_returns_404_not_500(app_client):
    token = _org(app_client, "notfound")
    h = {"Authorization": f"Bearer {token}"}

    for path in [
        f"/api/v1/returns/{uuid.uuid4()}",
        f"/api/v1/customers/{uuid.uuid4()}",
        f"/api/v1/ai/predictions/{uuid.uuid4()}/explain",
    ]:
        r = app_client.get(path, headers=h)
        assert r.status_code == 404, f"{path} returned {r.status_code}, expected 404"


def test_duplicate_registration_returns_409(app_client):
    email = f"dupe_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "full_name": "First", "email": email, "password": "TestPass123",
        "org_name": f"Org {uuid.uuid4().hex[:6]}", "platform_type": "shopify", "accepted_terms": True,
    }
    r1 = app_client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 200

    r2 = app_client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409, f"duplicate registration returned {r2.status_code}"


def test_error_responses_have_consistent_shape(app_client):
    """Every error must have a 'detail' field so clients can parse uniformly."""
    r = app_client.get("/api/v1/returns")   # 401
    assert "detail" in r.json()

    token = _org(app_client, "errshape")
    r = app_client.get(f"/api/v1/returns/{uuid.uuid4()}",
                       headers={"Authorization": f"Bearer {token}"})   # 404
    assert "detail" in r.json()


# ── Response content types ───────────────────────────────────────────────────

def test_json_endpoints_return_json_content_type(app_client):
    token = _org(app_client, "ctype")
    r = app_client.get("/api/v1/returns/dashboard",
                       headers={"Authorization": f"Bearer {token}"})
    assert r.headers["content-type"].startswith("application/json")


def test_request_id_header_echoed(app_client):
    """Phase 8.7 correlation IDs - client-supplied ID must be echoed back."""
    custom_id = "test-correlation-id-12345"
    r = app_client.get("/health", headers={"X-Request-ID": custom_id})
    assert r.headers.get("X-Request-ID") == custom_id


def test_request_id_generated_when_not_supplied(app_client):
    r = app_client.get("/health")
    assert r.headers.get("X-Request-ID"), "no request ID generated"


# ── Unknown categorical values: accepted but flagged (Phase 9.7 finding) ─────

@pytest.mark.parametrize("field,unknown_value", [
    ("courier", "FedEx"),
    ("item_category", "Automotive"),
    ("return_reason_code", "customer_regret"),
])
def test_unknown_categorical_accepted_but_flagged(app_client, field, unknown_value):
    """
    courier / item_category / return_reason_code are deliberately NOT strict
    enums: the feature_mapping layer accepts many aliases so that merchants
    with slightly different naming don't get hard failures.

    The risk is that an unrecognised value is silently normalised to "" and
    one-hot encoded as all-zeros - the prediction still returns a confident
    number while quietly being less accurate.

    So the contract is: accept the request, but tell the caller the
    prediction was degraded.
    """
    token = _org(app_client, "unmapped")
    payload = {
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "test@example.com",
        "sku": "SKU-1", "item_category": "Electronics", "item_value": 1000.0,
        "origin_pincode": "400001", "destination_pincode": "560001",
        "weight_grams": 1000, "volumetric_weight_grams": 1200,
        "return_reason_code": "defective", "courier": "BlueDart",
        "payment_mode": "Prepaid", "fragile": False, "festive": False,
        "condition": "good",
    }
    payload[field] = unknown_value

    r = app_client.post("/api/v1/returns",
                        headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert r.status_code in (200, 201), r.text

    body = r.json()
    assert "data_quality_warnings" in body, (
        f"unknown {field}={unknown_value!r} was silently accepted with no warning - "
        f"the caller has no way to know the prediction is degraded"
    )
    assert any(unknown_value in w for w in body["data_quality_warnings"])


def test_known_categorical_values_produce_no_warnings(app_client):
    """The happy path must stay clean - no spurious warnings."""
    token = _org(app_client, "mapped")
    r = app_client.post("/api/v1/returns",
                        headers={"Authorization": f"Bearer {token}"}, json={
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "test@example.com",
        "sku": "SKU-1", "item_category": "Electronics", "item_value": 1000.0,
        "origin_pincode": "400001", "destination_pincode": "560001",
        "weight_grams": 1000, "volumetric_weight_grams": 1200,
        "return_reason_code": "defective", "courier": "BlueDart",
        "payment_mode": "Prepaid", "fragile": False, "festive": False,
        "condition": "good",
    })
    assert r.status_code in (200, 201)
    assert "data_quality_warnings" not in r.json(), \
        "known-good values produced a spurious warning"


# ── Route shadowing regression (Phase 9 finding) ─────────────────────────────

def test_no_duplicate_route_paths_registered(app_client):
    """
    Two routers registering the same path is a silent, dangerous bug: FastAPI
    matches whichever was included first, so the later router's handler
    becomes unreachable dead code with no error at startup.

    This actually happened - misc.py defined GET /api/v1/customers and
    /api/v1/customers/{customer_id}, shadowing the richer Phase 5 handlers in
    customers.py (pagination, search, filters, analytics) for two phases.
    """
    from app.main import app

    seen: dict[tuple[str, str], str] = {}
    duplicates = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        endpoint = getattr(route, "endpoint", None)
        if not path or not methods:
            continue
        for method in methods:
            key = (method, path)
            name = f"{getattr(endpoint, '__module__', '?')}.{getattr(endpoint, '__name__', '?')}"
            if key in seen and seen[key] != name:
                duplicates.append(f"{method} {path}: {seen[key]} shadowed by {name}")
            else:
                seen[key] = name

    assert not duplicates, "duplicate route registrations:\n  " + "\n  ".join(duplicates)


def test_phase5_customer_endpoints_are_reachable(app_client):
    """
    Guards the specific regression above: the Phase 5 customers router must
    own /api/v1/customers/, not a legacy handler. The paginated response shape
    is the tell - the shadowing handler returned a bare list.
    """
    token = _org(app_client, "shadow")
    r = app_client.get("/api/v1/customers/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict), (
        "GET /api/v1/customers/ returned a list, not a paginated object - "
        "a legacy handler is shadowing the Phase 5 router again"
    )
    for field in ["items", "total", "page", "page_size"]:
        assert field in body, f"paginated response missing {field}"
