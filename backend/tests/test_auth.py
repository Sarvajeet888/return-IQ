"""Auth flow: register/login, refresh rotation + replay detection, lockout, logout revocation."""
from __future__ import annotations


def test_demo_login_works(app_client):
    r = app_client.post("/api/v1/auth/login", json={
        "email": "admin@sapnacollection.com", "password": "Demo@12345",
    })
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" not in body, "refresh token must never be returned in the JSON body"
    assert "rl_refresh_token" in r.cookies, "refresh token must be set as an httpOnly cookie"


def test_login_wrong_password_rejected(app_client, unique_email):
    r = app_client.post("/api/v1/auth/login", json={"email": unique_email, "password": "wrong"})
    assert r.status_code == 401


def test_register_then_me(registered_user):
    client, token, email, _ = registered_user
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email.lower()


def test_me_requires_auth(app_client):
    r = app_client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_account_lockout_after_max_attempts(app_client, unique_email):
    # register the account first so the email exists
    app_client.post("/api/v1/auth/register", json={
        "full_name": "Lockout Test", "email": unique_email, "password": "TestPass123",
        "org_name": "Lockout Org", "platform_type": "shopify", "accepted_terms": True,
    })
    for _ in range(3):
        r = app_client.post("/api/v1/auth/login", json={"email": unique_email, "password": "wrong"})
        assert r.status_code == 401
    # 4th attempt (even with the *correct* password) should now be locked out
    r = app_client.post("/api/v1/auth/login", json={"email": unique_email, "password": "TestPass123"})
    assert r.status_code == 429


def test_refresh_token_rotation_and_replay_detection(app_client, unique_email):
    password = "TestPass123"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Rotation Test", "email": unique_email, "password": password,
        "org_name": "Rotation Org", "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200
    old_cookie = r.cookies.get("rl_refresh_token")

    # normal refresh works and rotates the cookie
    r2 = app_client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200
    assert "access_token" in r2.json()

    # replaying the now-stale refresh token must fail (reuse/theft detection)
    r3 = app_client.post("/api/v1/auth/refresh", cookies={"rl_refresh_token": old_cookie})
    assert r3.status_code == 401


def test_logout_revokes_access_token(registered_user):
    client, token, _, _ = registered_user
    r = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    r2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 401, "access token must be unusable immediately after logout"


def test_secret_key_persists_across_process_restarts(tmp_path, monkeypatch):
    """SECRET_KEY must be stable across restarts in dev mode (the old bug
    generated a brand-new random key on every import, silently invalidating
    every previously-issued JWT)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")

    import importlib
    from app.core import config as config_module
    config_module.get_settings.cache_clear()
    s1 = config_module.get_settings()
    config_module.get_settings.cache_clear()
    s2 = config_module.get_settings()
    assert s1.SECRET_KEY == s2.SECRET_KEY


def test_secret_key_required_in_production(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    from app.core import config as config_module
    config_module.get_settings.cache_clear()
    import pytest
    with pytest.raises(RuntimeError):
        config_module.get_settings()
    monkeypatch.setenv("ENVIRONMENT", "test")
    config_module.get_settings.cache_clear()
