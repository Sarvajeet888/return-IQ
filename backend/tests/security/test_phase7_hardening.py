"""PHASE 7 — Security headers, upload content verification, storage failure modes."""
from __future__ import annotations

import io
import struct
import uuid
import zlib
from unittest.mock import patch

import pytest


# ────────────────────────────── security headers ─────────────────────────────

def test_security_headers_present(app_client):
    r = app_client.get("/api/v1/health")
    h = {k.lower(): v for k, v in r.headers.items()}

    assert h["x-frame-options"] == "DENY"
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "strict-origin-when-cross-origin"


def test_csp_denies_everything_by_default(app_client):
    """The API serves JSON. Nothing should ever load or execute from it, so
    the strictest policy is also the correct one."""
    r = app_client.get("/api/v1/health")
    csp = r.headers["content-security-policy"]

    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'none'" in csp
    # A policy that permits inline script on an API is almost always a
    # copy-paste from a frontend config.
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp


def test_cross_origin_isolation_headers(app_client):
    r = app_client.get("/api/v1/health")
    h = {k.lower(): v for k, v in r.headers.items()}
    assert h["cross-origin-opener-policy"] == "same-origin"
    assert h["cross-origin-resource-policy"] == "same-origin"


def test_headers_present_on_errors_too(app_client):
    """Error responses are responses. A 404 without CSP is still a 404 a
    browser will happily frame."""
    r = app_client.get("/api/v1/definitely-not-a-route")
    assert r.status_code == 404
    assert "content-security-policy" in {k.lower() for k in r.headers}


# ─────────────────────── upload content verification ─────────────────────────

@pytest.fixture
def authed(app_client):
    email = f"sec_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Sec Tester", "email": email, "password": "SecPass123",
        "org_name": f"Sec Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _valid_png() -> bytes:
    """A realistically-sized PNG.

    libmagic parses structure, not just the signature -- an 8-byte header
    followed by nulls is detected as application/octet-stream and correctly
    rejected. Building a genuine file keeps the control test honest.

    PHASE 22: originally 1x1. The upload path now validates that an evidence
    image is large enough to show damage, and correctly rejected it. The
    fixture changed, not the rule.
    """
    from PIL import Image
    img = Image.new("RGB", (400, 300), (100, 140, 180))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _create_return(app_client, headers) -> str:
    r = app_client.post("/api/v1/returns", headers=headers, json={
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "cust-1",
        "sku": "SKU-1", "item_category": "Electronics", "item_value": "1500.00",
        "origin_pincode": "400001", "destination_pincode": "411001",
        "weight_grams": 500, "volumetric_weight_grams": 600,
        "return_reason_code": "damaged", "courier": "Delhivery",
        "payment_mode": "COD", "fragile": False, "festive": False,
        "condition": "good",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_executable_disguised_as_image_is_rejected(app_client, authed):
    """The attack the Content-Type header cannot stop.

    `Content-Type: image/png` and a `.png` filename are both written by the
    client. Only the bytes are trustworthy -- and these begin with `MZ`, the
    DOS/PE executable signature.
    """
    return_id = _create_return(app_client, authed)
    payload = b"MZ\x90\x00" + b"\x00" * 512

    r = app_client.post(
        f"/api/v1/returns/{return_id}/documents",
        headers=authed,
        files={"file": ("holiday_photo.png", io.BytesIO(payload), "image/png")},
    )
    assert r.status_code == 400
    assert "content" in r.json()["detail"].lower()


def test_genuine_png_is_accepted(app_client, authed):
    """Control: verification must not reject legitimate evidence photos."""
    return_id = _create_return(app_client, authed)
    png = _valid_png()

    r = app_client.post(
        f"/api/v1/returns/{return_id}/documents",
        headers=authed,
        files={"file": ("damage.png", io.BytesIO(png), "image/png")},
    )
    assert r.status_code == 201, r.text


def test_html_disguised_as_image_is_rejected(app_client, authed):
    """Stored-XSS vector: an HTML file served back from a document endpoint."""
    return_id = _create_return(app_client, authed)
    payload = b"<html><script>alert(document.cookie)</script></html>"

    r = app_client.post(
        f"/api/v1/returns/{return_id}/documents",
        headers=authed,
        files={"file": ("invoice.jpg", io.BytesIO(payload), "image/jpeg")},
    )
    assert r.status_code == 400


# ──────────────────────── storage failure containment ────────────────────────

def test_unexpected_storage_error_returns_false_not_raises():
    """PHASE 7 fix.

    Only BotoCoreError/ClientError were caught, so a DNS failure surfacing as
    socket.gaierror, an SSL error, or an exception type boto does not
    re-export escaped a function whose contract is 'returns True on success'.
    The caller checks the boolean and raises a clean 500; an escaping
    exception produced an unhandled error instead.
    """
    from app.services import storage_service

    with patch.object(storage_service, "_local_root", side_effect=Exception("disk on fire")):
        assert storage_service.store_file("k", b"data", "text/plain") is False


def test_upload_failure_surfaces_as_clean_500(app_client, authed):
    """A storage outage must not leak a stack trace to the client."""
    from app.services import storage_service

    return_id = _create_return(app_client, authed)
    png = _valid_png()

    with patch.object(storage_service, "store_file", return_value=False):
        r = app_client.post(
            f"/api/v1/returns/{return_id}/documents",
            headers=authed,
            files={"file": ("damage.png", io.BytesIO(png), "image/png")},
        )
    assert r.status_code == 500
    assert "Traceback" not in r.text
