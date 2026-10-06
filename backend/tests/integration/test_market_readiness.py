"""
Tests for the four market-readiness features (Phase 12):
SMTP, consent capture, PII encryption, and file storage.

Each closed a known issue that would have blocked a real customer, so each
gets tests that prove the fix rather than just exercise the code path.
"""
from __future__ import annotations
import uuid
from unittest.mock import MagicMock, patch


def _register(client, **overrides):
    payload = {
        "full_name": "Consent User",
        "email": f"c_{uuid.uuid4().hex[:8]}@example.com",
        "password": "TestPass123",
        "org_name": f"ConsentOrg {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify",
        "accepted_terms": True,
    }
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload), payload


# ── Consent capture (DPDP Act) ───────────────────────────────────────────────

def test_registration_requires_accepted_terms(app_client):
    """Omitting consent must fail - it cannot be an optional field."""
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "No Consent",
        "email": f"nc_{uuid.uuid4().hex[:8]}@example.com",
        "password": "TestPass123",
        "org_name": f"Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify",
    })
    assert r.status_code == 422, "registration succeeded without consent - DPDP violation"
    assert "accepted_terms" in r.text


def test_registration_rejects_explicit_false_consent(app_client):
    r, _ = _register(app_client, accepted_terms=False)
    assert r.status_code == 422


def test_consent_record_is_written_on_registration(app_client):
    """
    The DPDP Act requires a Data Fiduciary to DEMONSTRATE consent, not merely
    assert it. A record must exist after registration.
    """
    r, payload = _register(app_client)
    assert r.status_code == 200, r.text

    from app.db import store
    user = store.get_user_by_email(payload["email"])
    history = store.get_consent_history(user["id"])

    assert len(history) >= 1, "no consent record written - cannot prove consent was given"
    rec = history[0]
    assert rec["granted"] is True
    assert rec["consent_type"] == "terms_and_privacy"
    assert rec["policy_version"], "policy version missing - cannot prove WHAT was accepted"
    assert rec["created_at"], "timestamp missing - cannot prove WHEN"


def test_consent_records_policy_version(app_client):
    r, payload = _register(app_client, policy_version="2.1")
    assert r.status_code == 200
    from app.db import store
    user = store.get_user_by_email(payload["email"])
    assert store.get_consent_history(user["id"])[0]["policy_version"] == "2.1"


def test_has_valid_consent_helper(app_client):
    r, payload = _register(app_client)
    from app.db import store
    user = store.get_user_by_email(payload["email"])
    assert store.has_valid_consent(user["id"]) is True


def test_consent_withdrawal_is_append_only(app_client):
    """Withdrawal writes a new row rather than mutating - history stays auditable."""
    r, payload = _register(app_client)
    from app.db import store
    user = store.get_user_by_email(payload["email"])

    store.record_consent({
        "user_id": user["id"], "consent_type": "terms_and_privacy",
        "policy_version": "1.0", "granted": False,
    })

    history = store.get_consent_history(user["id"])
    assert len(history) == 2, "withdrawal overwrote the original record"
    assert store.has_valid_consent(user["id"]) is False
    assert any(h["granted"] for h in history), "original grant was lost"


# ── PII encryption at rest ───────────────────────────────────────────────────

def test_encryption_roundtrip():
    from app.core.encryption import encrypt_value, decrypt_value
    ct = encrypt_value("customer@example.com")
    assert ct != "customer@example.com", "value was not encrypted"
    assert decrypt_value(ct) == "customer@example.com"


def test_encryption_is_non_deterministic():
    """
    Identical plaintext must produce different ciphertext (random IV). This is
    what makes the encryption sound - and what makes SQL LIKE search impossible.
    """
    from app.core.encryption import encrypt_value
    assert encrypt_value("same@example.com") != encrypt_value("same@example.com")


def test_decrypt_tolerates_plaintext():
    """Pre-encryption rows must pass through unchanged during rollout."""
    from app.core.encryption import decrypt_value
    assert decrypt_value("legacy-plaintext-value") == "legacy-plaintext-value"


def test_encryption_handles_none_and_empty():
    from app.core.encryption import encrypt_value, decrypt_value
    assert encrypt_value(None) is None
    assert encrypt_value("") == ""
    assert decrypt_value(None) is None


def test_customer_pii_is_ciphertext_in_the_database(app_client):
    """
    THE test that proves KI-002 is closed: read the raw column and confirm the
    plaintext is not there. If this fails, a stolen dump exposes every customer.
    """
    from sqlalchemy import text
    from app.db.database import SessionLocal

    r, _ = _register(app_client)
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    secret_email = f"pii_{uuid.uuid4().hex[:8]}@secret.com"
    created = app_client.post("/api/v1/customers/", headers=h, json={
        "name": "Sensitive Name", "email": secret_email,
        "phone": "9999888877", "city": "Mumbai",
    })
    assert created.status_code == 201, created.text

    with SessionLocal() as db:
        rows = db.execute(text("SELECT name, email, phone FROM customers")).fetchall()

    raw = " ".join(str(v) for row in rows for v in row)
    assert secret_email not in raw, "PLAINTEXT PII IN DATABASE - KI-002 not closed"
    assert "Sensitive Name" not in raw, "plaintext customer name in database"
    assert "9999888877" not in raw, "plaintext phone number in database"


def test_customer_pii_reads_back_correctly(app_client):
    """Encryption must be transparent to the application."""
    r, _ = _register(app_client)
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    email = f"rt_{uuid.uuid4().hex[:8]}@example.com"
    cid = app_client.post("/api/v1/customers/", headers=h, json={
        "name": "Round Trip", "email": email, "phone": "9876543210", "city": "Pune",
    }).json()["id"]

    body = app_client.get(f"/api/v1/customers/{cid}", headers=h).json()
    assert body["email"] == email
    assert body["name"] == "Round Trip"
    assert body["phone"] == "9876543210"


def test_customer_search_still_works_on_encrypted_columns(app_client):
    """Search moved from SQL LIKE to in-Python filtering - verify it still finds people."""
    r, _ = _register(app_client)
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    app_client.post("/api/v1/customers/", headers=h, json={
        "name": "Findable Person", "email": "findable@example.com",
        "phone": "1112223334", "city": "Delhi",
    })

    found = app_client.get("/api/v1/customers/?search=Findable", headers=h)
    assert found.status_code == 200
    assert any(c["name"] == "Findable Person" for c in found.json()["items"]), \
        "search returned nothing - encrypted-column search is broken"


def test_customer_search_is_org_scoped(app_client):
    """Search decrypts in Python - the org filter must still hold."""
    r_a, _ = _register(app_client)
    r_b, _ = _register(app_client)
    h_a = {"Authorization": f"Bearer {r_a.json()['access_token']}"}
    h_b = {"Authorization": f"Bearer {r_b.json()['access_token']}"}

    app_client.post("/api/v1/customers/", headers=h_a, json={
        "name": "Org A Secret", "email": "orga_secret@example.com",
        "phone": "5556667778", "city": "Chennai",
    })

    leaked = app_client.get("/api/v1/customers/?search=Secret", headers=h_b)
    assert "Org A Secret" not in leaked.text, "CROSS-TENANT LEAK in customer search"


# ── Email service ────────────────────────────────────────────────────────────

def test_email_service_reports_unconfigured_by_default():
    from app.services import email_service
    assert email_service.is_configured() is False


def test_send_email_returns_false_when_unconfigured(app_client):
    """A dead or absent SMTP server must never turn a request into a 500."""
    from app.services import email_service
    assert email_service.send_email("a@b.com", "s", "body") is False


def test_send_email_swallows_smtp_errors():
    from app.services import email_service
    with patch.object(email_service, "is_configured", return_value=True), \
         patch("smtplib.SMTP", side_effect=OSError("connection refused")):
        assert email_service.send_email("a@b.com", "s", "body") is False


def test_password_reset_email_contains_a_working_link():
    from app.services import email_service
    sent = {}

    def capture(to, subject, text, html=None):
        sent.update(to=to, subject=subject, text=text)
        return True

    with patch.object(email_service, "send_email", side_effect=capture):
        email_service.send_password_reset("u@example.com", "TOK123", "https://app.example.com")

    assert "https://app.example.com/reset-password?token=TOK123" in sent["text"]
    assert "expires" in sent["text"].lower()


def test_forgot_password_still_succeeds_without_smtp(app_client):
    """Must not fail because email is unconfigured, and must not leak existence."""
    r = app_client.post("/api/v1/users/forgot-password",
                        json={"email": f"nobody_{uuid.uuid4().hex}@example.com"})
    assert r.status_code == 200
    assert "not found" not in r.json()["message"].lower()


def test_invite_email_carries_a_link_not_a_password():
    """PHASE 5: this test previously asserted the vulnerability was present.

    It checked that the invitation email contained `Welcome@abc123` -- i.e.
    that a working, reusable credential was sitting in the recipient's inbox.
    It now asserts the opposite property: the email carries a single-use link
    and no password at all.
    """
    from app.services import email_service
    sent = {}
    accept_url = "https://app.example.com/accept-invitation?token=abc123xyz"
    with patch.object(email_service, "send_email",
                      side_effect=lambda to, s, t, h=None: sent.update(text=t) or True):
        email_service.send_team_invitation(
            "new@example.com", "New Person", "Acme Returns", accept_url)

    assert accept_url in sent["text"]
    assert "Acme Returns" in sent["text"]
    # No password is set for the invitee, so nothing can be leaked by the email.
    assert "password:" not in sent["text"].lower()
    assert "temporary password" not in sent["text"].lower()
    # The single-use, time-bounded nature should be stated to the recipient.
    assert "once" in sent["text"].lower()


# ── File storage ─────────────────────────────────────────────────────────────

def test_storage_defaults_to_local_backend():
    from app.services import storage_service
    assert storage_service.is_s3_enabled() is False
    assert storage_service.backend_name().startswith("local:")


def test_storage_key_is_org_scoped_and_unique():
    from app.services import storage_service
    k1 = storage_service.build_storage_key("ORG1", "RET1", "photo.jpg")
    k2 = storage_service.build_storage_key("ORG1", "RET1", "photo.jpg")
    assert k1.startswith("uploads/ORG1/RET1/")
    assert k1 != k2, "same filename produced the same key - uploads could overwrite"


def test_storage_key_strips_path_traversal():
    """A filename must never be able to escape its directory."""
    from app.services import storage_service
    key = storage_service.build_storage_key("ORG1", "RET1", "../../../etc/passwd")
    assert ".." not in key, f"path traversal survived: {key}"
    assert key.startswith("uploads/ORG1/RET1/")


def test_local_storage_roundtrip(tmp_path):
    from app.services import storage_service
    with patch.object(storage_service, "_local_root", return_value=tmp_path):
        key = "uploads/ORG1/RET1/test.txt"
        assert storage_service.store_file(key, b"hello bytes", "text/plain") is True
        assert storage_service.read_file(key) == b"hello bytes"
        assert storage_service.delete_file(key) is True
        assert storage_service.read_file(key) is None


def test_s3_used_when_bucket_configured():
    from app.services import storage_service
    fake = MagicMock()
    with patch.object(storage_service, "_bucket", return_value="my-bucket"), \
         patch.object(storage_service, "_BOTO_AVAILABLE", True), \
         patch.object(storage_service, "_get_s3", return_value=fake):
        assert storage_service.store_file("k", b"data", "text/plain") is True
        kwargs = fake.put_object.call_args.kwargs
        assert kwargs["Bucket"] == "my-bucket"
        assert kwargs["ServerSideEncryption"] == "AES256", "S3 object not server-side encrypted"


def test_s3_failure_returns_false_not_raises():
    from app.services import storage_service
    fake = MagicMock()
    fake.put_object.side_effect = Exception("network down")
    with patch.object(storage_service, "_bucket", return_value="b"), \
         patch.object(storage_service, "_BOTO_AVAILABLE", True), \
         patch.object(storage_service, "_get_s3", return_value=fake):
        assert storage_service.store_file("k", b"d", "text/plain") is False


def test_uploaded_file_is_actually_persisted(app_client, tmp_path):
    """
    KI-011: the endpoint recorded a storage_key in the database while never
    writing the bytes anywhere. Verify the file now exists on disk.
    """
    from app.services import storage_service

    r, _ = _register(app_client)
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    return_id = app_client.post("/api/v1/returns", headers=h, json={
        "platform_order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "customer_identifier": "up@example.com", "sku": "SKU-UP",
        "item_category": "Electronics", "item_value": 5000.0,
        "origin_pincode": "400001", "destination_pincode": "560001",
        "weight_grams": 1000, "volumetric_weight_grams": 1200,
        "return_reason_code": "defective", "courier": "BlueDart",
        "payment_mode": "Prepaid", "fragile": False, "festive": False,
        "condition": "good",
    }).json()["id"]

    # A real PNG. The upload endpoint validates by magic bytes
    # (python-magic), not the declared content-type, so a fake header is
    # correctly rejected - that is the Phase 6 security control working.
    #
    # PHASE 22: this was a 1x1 PNG. Evidence images are now checked for enough
    # detail to show damage, and 1x1 was correctly rejected. The fixture
    # changed, not the rule.
    import io as _io

    from PIL import Image as _Image

    _buf = _io.BytesIO()
    _Image.new("RGB", (400, 300), (100, 140, 180)).save(_buf, "PNG")
    png = _buf.getvalue()

    with patch.object(storage_service, "_local_root", return_value=tmp_path):
        up = app_client.post(
            f"/api/v1/returns/{return_id}/documents",
            headers=h,
            files={"file": ("damage.png", png, "image/png")},
            data={"is_damage_photo": "true"},
        )
        assert up.status_code == 201, up.text
        stored = tmp_path / up.json()["storage_key"]
        assert stored.exists(), "storage_key recorded but no file written - KI-011 not closed"
        assert stored.read_bytes() == png, "stored bytes do not match the upload"
