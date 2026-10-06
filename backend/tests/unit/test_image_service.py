"""PHASE 22 — evidence image processing.

The property under test: no identifying metadata reaches storage, and the
image remains usable for human review and future computer vision.
"""
from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from app.services.image_service import (
    MAX_DIMENSION,
    MIN_DIMENSION,
    ImageProcessingError,
    inspect_metadata,
    process_evidence_image,
)


def _photo(width=1600, height=1200, *, with_exif=True, orientation=None, fmt="JPEG"):
    """A JPEG resembling what a phone camera produces."""
    img = Image.new("RGB", (width, height), (130, 120, 110))
    buf = io.BytesIO()

    if with_exif:
        exif = img.getexif()
        exif[271] = "Apple"
        exif[272] = "iPhone 14 Pro"
        exif[305] = "iOS 18.2"
        exif[306] = "2026:08:10 14:23:11"
        exif[34853] = {1: "N", 2: (19, 4, 45)}       # GPS block
        if orientation:
            exif[274] = orientation
        img.save(buf, fmt, exif=exif.tobytes())
    else:
        img.save(buf, fmt)

    return buf.getvalue()


# ───────────────────────── the privacy defect ────────────────────────────────

def test_a_phone_photo_carries_identifying_metadata():
    """Establishing the problem before testing the fix.

    Verified in this environment: no code path in ReturnIQ removed any of
    this, and Pillow was not even a dependency.
    """
    report = inspect_metadata(_photo())
    assert report["has_location"] is True
    names = {t["name"] for t in report["tags"]}
    assert "GPS block (latitude, longitude, altitude)" in names
    assert "Camera make" in names


def test_processing_removes_the_location():
    """THE test for this phase.

    A merchant asking for a photo of a damaged shirt should not receive the
    customer's home coordinates.
    """
    processed = process_evidence_image(_photo())
    after = inspect_metadata(processed.content)

    assert after["has_location"] is False
    assert after["has_metadata"] is False
    assert after["total_exif_fields"] == 0


def test_every_identifying_field_is_removed():
    processed = process_evidence_image(_photo())
    assert inspect_metadata(processed.content)["tags"] == []


def test_what_was_stripped_is_reported():
    """A merchant who can see the fields removed from their own archive
    understands the issue immediately."""
    processed = process_evidence_image(_photo())
    assert "GPS block (latitude, longitude, altitude)" in processed.stripped_tags
    assert "removed before storage" in processed.as_dict()["privacy_note"]


def test_an_image_without_metadata_reports_cleanly():
    processed = process_evidence_image(_photo(with_exif=False))
    assert processed.stripped_tags == []
    assert "No identifying metadata" in processed.as_dict()["privacy_note"]


def test_inspect_returns_a_consistent_shape_whether_or_not_metadata_exists():
    """My first version returned a shorter dict when EXIF was absent, so
    callers hit KeyError on a successfully stripped image — the clean path
    was the one that broke."""
    dirty = inspect_metadata(_photo())
    clean = inspect_metadata(process_evidence_image(_photo()).content)
    assert set(dirty) == set(clean)


# ──────────────────────── image stays usable ─────────────────────────────────

def test_orientation_is_applied_before_the_flag_is_discarded():
    """Phones record 'rotate 90 degrees' as metadata rather than rotating
    pixels. Strip the metadata without applying it and every portrait photo is
    stored sideways — breaking human review, and teaching a future CV model
    that damage appears at arbitrary rotations.
    """
    landscape = _photo(1600, 1200, orientation=6)      # 6 = rotate 90
    processed = process_evidence_image(landscape)

    assert processed.was_reoriented is True
    assert processed.height > processed.width          # now genuinely portrait


def test_oversized_images_are_downscaled():
    """A 48MP photo of a torn t-shirt carries no more damage information than
    a 2MP one, and multiplies storage cost and inference latency."""
    processed = process_evidence_image(_photo(6000, 4000))
    assert max(processed.width, processed.height) == MAX_DIMENSION
    assert processed.was_resized is True
    assert len(processed.content) < processed.original_bytes


def test_aspect_ratio_is_preserved_when_downscaling():
    processed = process_evidence_image(_photo(4000, 2000))
    assert processed.width / processed.height == pytest.approx(2.0, abs=0.02)


def test_a_normal_sized_image_is_not_upscaled():
    processed = process_evidence_image(_photo(800, 600))
    assert (processed.width, processed.height) == (800, 600)
    assert processed.was_resized is False


def test_the_image_is_still_a_valid_readable_image():
    """Stripping must not corrupt the evidence."""
    processed = process_evidence_image(_photo())
    reopened = Image.open(io.BytesIO(processed.content))
    reopened.load()
    assert reopened.size == (processed.width, processed.height)


def test_png_stays_png():
    """Silently converting formats would surprise anyone downloading their
    own evidence."""
    processed = process_evidence_image(_photo(800, 600, with_exif=False, fmt="PNG"))
    assert processed.format == "PNG"


# ──────────────────────────── rejections ─────────────────────────────────────

def test_a_tiny_image_is_rejected():
    """Below this an image cannot show damage detail. Better to reject at
    upload than accept it and find it useless during inspection."""
    with pytest.raises(ImageProcessingError, match=str(MIN_DIMENSION)):
        process_evidence_image(_photo(100, 80, with_exif=False))


def test_a_corrupted_file_is_rejected_with_a_readable_message():
    with pytest.raises(ImageProcessingError, match="could not be read"):
        process_evidence_image(b"\xff\xd8\xff" + b"garbage" * 100)


# ─────────────────────────── end-to-end upload ───────────────────────────────

@pytest.fixture
def authed(app_client):
    email = f"img_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Image Tester", "email": email, "password": "ImagePass123",
        "org_name": f"Img Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    rr = app_client.post("/api/v1/returns", headers=headers, json={
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "c1", "sku": "S1", "item_category": "apparel",
        "item_value": "1500.00", "origin_pincode": "400001",
        "destination_pincode": "411001", "weight_grams": 500,
        "volumetric_weight_grams": 600, "return_reason_code": "damaged",
        "courier": "Delhivery", "payment_mode": "COD",
        "fragile": False, "festive": False, "condition": "good",
    })
    assert rr.status_code in (200, 201), rr.text
    return app_client, headers, rr.json()["id"]


def test_uploaded_photos_are_stripped_before_storage(authed):
    """End-to-end proof: a customer's GPS coordinates must not survive the
    upload path."""
    client, headers, return_id = authed

    r = client.post(
        f"/api/v1/returns/{return_id}/documents",
        headers=headers,
        files={"file": ("damage.jpg", io.BytesIO(_photo()), "image/jpeg")},
        data={"source": "customer", "evidence_type": "damage_photo"},
    )
    assert r.status_code == 201, r.text

    meta = r.json()["image_processing"]
    assert "GPS block (latitude, longitude, altitude)" in meta["stripped_metadata"]
    assert "removed before storage" in meta["privacy_note"]


def test_the_stored_hash_is_of_the_cleaned_file(authed):
    """The integrity claim is about the file in storage, so the hash must
    cover what we keep — not what arrived and was then modified."""
    client, headers, return_id = authed
    raw = _photo()

    r = client.post(
        f"/api/v1/returns/{return_id}/documents",
        headers=headers,
        files={"file": ("damage.jpg", io.BytesIO(raw), "image/jpeg")},
    )
    assert r.status_code == 201

    from app.services.evidence_service import content_hash
    assert r.json()["content_sha256"] != content_hash(raw)
    assert r.json()["content_sha256"] == content_hash(
        process_evidence_image(raw).content
    )
