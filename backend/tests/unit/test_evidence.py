"""PHASE 13 — evidence integrity, provenance, and reuse detection."""
from __future__ import annotations

import io
import struct
import uuid
import zlib

import pytest

from app.services import evidence_service as ev
from app.services.evidence_service import EvidenceSource, EvidenceType


def _valid_png(seed: int = 0) -> bytes:
    """A realistically-sized PNG. `seed` varies the pixels so two calls differ.

    PHASE 22 note: these fixtures were originally 1x1 pixels, which is fine
    for testing magic-byte detection and hashing. Once evidence images began
    being validated for usable detail, the upload endpoint correctly rejected
    them: "This image is 1x1. Evidence photos need to be at least 200px."

    The rule is right — a 1x1 "damage photo" is not evidence of anything — so
    the fixture changed, not the rule. Worth recording, because the tempting
    move when six tests fail at once is to relax the new check.
    """
    from PIL import Image
    img = Image.new("RGB", (400, 300), (seed % 256, 120, 200))
    # Vary a pixel block so different seeds produce different content hashes.
    for x in range(10):
        for y in range(10):
            img.putpixel((x, y), ((seed * 7) % 256, (seed * 13) % 256, 90))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ────────────────────────────── content hashing ──────────────────────────────

def test_identical_bytes_hash_identically():
    a, b = _valid_png(1), _valid_png(1)
    assert ev.content_hash(a) == ev.content_hash(b)


def test_a_single_byte_difference_changes_the_hash():
    assert ev.content_hash(_valid_png(1)) != ev.content_hash(_valid_png(2))


def test_hash_is_sha256_not_md5():
    """MD5 collisions are constructible on a laptop. For a dedup cache that
    would be a curiosity; for a value cited as evidence in a dispute it means
    someone can argue the hash proves nothing."""
    assert len(ev.content_hash(b"x")) == 64


def test_hash_detects_substituted_storage_content():
    """The integrity claim: the stored bytes are the uploaded bytes.

    Without this, "the customer sent us this photo" is an assertion — anyone
    with storage access could swap the file and nobody could tell.
    """
    original = _valid_png(1)
    recorded = ev.content_hash(original)

    tampered = _valid_png(2)          # someone replaces the object in storage
    assert ev.content_hash(tampered) != recorded


# ───────────────────────────── reuse detection ───────────────────────────────

def _doc(doc_id: str, return_id: str, file_hash: str, source: str = "customer") -> dict:
    return {
        "id": doc_id,
        "return_request_id": return_id,
        "content_sha256": file_hash,
        "source": source,
        "created_at": "2026-08-01T10:00:00",
    }


def test_no_reuse_when_the_file_is_new():
    result = ev.check_reuse([], "abc123", "return-1")
    assert result["reused"] is False
    assert result["match_count"] == 0


def test_same_file_on_the_same_return_is_not_flagged():
    """Benign: a customer re-uploading after a failed submission, or attaching
    the same photo twice. Flagging it would train staff to ignore the warning.
    """
    h = "hash-abc"
    existing = [_doc("d1", "return-1", h)]
    assert ev.check_reuse(existing, h, "return-1")["reused"] is False


def test_same_file_on_a_different_return_is_flagged():
    """THE fraud pattern this phase exists to surface.

    One broken item, photographed once, claimed against repeatedly. Invisible
    to a model trained on order attributes, because each individual order
    looks entirely ordinary.
    """
    h = "hash-abc"
    existing = [_doc("d1", "return-1", h), _doc("d2", "return-2", h)]
    result = ev.check_reuse(existing, h, "return-3")

    assert result["reused"] is True
    assert result["match_count"] == 2
    assert {m["return_request_id"] for m in result["matches"]} == {"return-1", "return-2"}


def test_different_files_are_not_flagged():
    existing = [_doc("d1", "return-1", "hash-other")]
    assert ev.check_reuse(existing, "hash-abc", "return-2")["reused"] is False


def test_finding_is_advisory_not_a_rejection():
    """The result describes; it does not decide.

    A customer with two genuinely identical returns — same product, same
    defect, same photo taken once — exists. Auto-rejecting them creates a
    support ticket the merchant cannot answer.
    """
    h = "hash-abc"
    result = ev.check_reuse([_doc("d1", "r1", h)], h, "r2")
    assert "note" in result
    assert "worth a look" in result["note"].lower()


def test_matches_are_capped_to_stay_a_finding():
    h = "hash-abc"
    existing = [_doc(f"d{i}", f"return-{i}", h) for i in range(50)]
    result = ev.check_reuse(existing, h, "return-current")
    assert result["match_count"] == 50          # the count is honest
    assert len(result["matches"]) == 10         # the payload is not a data dump


def test_documents_without_a_hash_never_match():
    """Pre-Phase-13 rows have NULL content_sha256 and must not collide with
    each other just because both are missing."""
    legacy = [{"id": "d1", "return_request_id": "r1", "content_sha256": None}]
    assert ev.check_reuse(legacy, "hash-abc", "r2")["reused"] is False


# ────────────────────────── provenance validation ────────────────────────────

def test_valid_sources_accepted():
    for source in (EvidenceSource.CUSTOMER, EvidenceSource.WAREHOUSE, EvidenceSource.INSPECTOR):
        assert ev.validate_source(source) == source


def test_unknown_source_is_refused_by_name():
    with pytest.raises(ValueError, match="not a valid evidence source"):
        ev.validate_source("anonymous_tipster")


def test_source_defaults_to_merchant():
    assert ev.validate_source(None) == EvidenceSource.MERCHANT


def test_unknown_evidence_type_is_refused():
    with pytest.raises(ValueError, match="not a valid evidence type"):
        ev.validate_type("blurry_thing")


def test_type_defaults_to_other():
    assert ev.validate_type(None) == EvidenceType.OTHER


# ──────────────────────────────── HTTP layer ─────────────────────────────────

@pytest.fixture
def authed_return(app_client):
    email = f"ev_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Evidence Tester", "email": email, "password": "EvidPass123",
        "org_name": f"Ev Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    def make_return():
        rr = app_client.post("/api/v1/returns", headers=headers, json={
            "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
            "customer_identifier": "c1", "sku": "S1", "item_category": "apparel",
            "item_value": "1000.00", "origin_pincode": "400001",
            "destination_pincode": "411001", "weight_grams": 500,
            "volumetric_weight_grams": 600, "return_reason_code": "damaged",
            "courier": "Delhivery", "payment_mode": "COD",
            "fragile": False, "festive": False, "condition": "good",
        })
        assert rr.status_code in (200, 201), rr.text
        return rr.json()["id"]

    return app_client, headers, make_return


def test_upload_records_hash_and_provenance(authed_return):
    client, headers, make_return = authed_return
    return_id = make_return()

    r = client.post(
        f"/api/v1/returns/{return_id}/documents",
        headers=headers,
        files={"file": ("damage.png", io.BytesIO(_valid_png(1)), "image/png")},
        data={"source": "customer", "evidence_type": "damage_photo"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["content_sha256"]) == 64
    assert body["source"] == "customer"
    assert body["evidence_type"] == "damage_photo"


def test_upload_stores_the_verified_type_not_the_claim(authed_return):
    """PHASE 13 fix.

    The row previously recorded `file.content_type` — the client's header —
    while the object store held the magic-byte-verified type. Both pass the
    same allow-list, so it was not exploitable, but a value nobody verified
    should not be the one we keep.
    """
    client, headers, make_return = authed_return
    return_id = make_return()

    r = client.post(
        f"/api/v1/returns/{return_id}/documents",
        headers=headers,
        # Claims JPEG; the bytes are a PNG.
        files={"file": ("photo.jpg", io.BytesIO(_valid_png(1)), "image/jpeg")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["file_type"] == "image/png"          # verified
    assert r.json()["declared_file_type"] == "image/jpeg"  # what was claimed


def test_reuse_across_returns_is_surfaced(authed_return):
    """End-to-end: the same photo attached to two different returns."""
    client, headers, make_return = authed_return
    photo = _valid_png(7)

    first = make_return()
    r1 = client.post(f"/api/v1/returns/{first}/documents", headers=headers,
                     files={"file": ("d.png", io.BytesIO(photo), "image/png")},
                     data={"source": "customer", "evidence_type": "damage_photo"})
    assert r1.status_code == 201
    assert "reuse_warning" not in r1.json()

    second = make_return()
    r2 = client.post(f"/api/v1/returns/{second}/documents", headers=headers,
                     files={"file": ("d.png", io.BytesIO(photo), "image/png")},
                     data={"source": "customer", "evidence_type": "damage_photo"})
    assert r2.status_code == 201
    warning = r2.json()["reuse_warning"]
    assert warning["reused"] is True
    assert warning["match_count"] == 1


def test_invalid_source_is_rejected(authed_return):
    client, headers, make_return = authed_return
    return_id = make_return()
    r = client.post(f"/api/v1/returns/{return_id}/documents", headers=headers,
                    files={"file": ("d.png", io.BytesIO(_valid_png(1)), "image/png")},
                    data={"source": "anonymous_tipster"})
    assert r.status_code == 422
