"""Google sign-in, customer records and sessions (FR-AU-*)."""
import sqlite3

import pytest

from server import create_app
from tests.conftest import Api, app_config


def make_verifier(info=None, error=None):
    def verify(credential):
        if error:
            raise error
        return info

    return verify


def google_info(**overrides):
    return {"email": "asha@gmail.com", "email_verified": True, "name": "Asha Rao", "picture": "http://pic/a.png", "sub": "g-123", **overrides}


def db_rows(app, sql):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


def test_google_login_creates_customer_record_and_session(app, anon):
    app.extensions["google_verifier"] = make_verifier(google_info())
    response = anon.post("/api/auth/google", json={"credential": "token"})
    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == "asha@gmail.com"
    assert "urlovingly_session" in response.headers["Set-Cookie"]

    users = db_rows(app, "SELECT email, name, picture, google_sub FROM users")
    assert users == [{"email": "asha@gmail.com", "name": "Asha Rao", "picture": "http://pic/a.png", "google_sub": "g-123"}]


def test_session_cookie_is_http_only_and_same_site(app, anon):
    app.extensions["google_verifier"] = make_verifier(google_info())
    cookie = anon.post("/api/auth/google", json={"credential": "t"}).headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_session_token_is_stored_hashed(app, anon):
    app.extensions["google_verifier"] = make_verifier(google_info())
    cookie = anon.post("/api/auth/google", json={"credential": "t"}).headers["Set-Cookie"]
    raw = cookie.split("urlovingly_session=")[1].split(";")[0]
    stored = db_rows(app, "SELECT token_hash FROM sessions")[0]["token_hash"]
    assert raw not in stored and len(stored) == 64


def test_returning_customer_is_not_duplicated(app, anon):
    app.extensions["google_verifier"] = make_verifier(google_info())
    anon.post("/api/auth/google", json={"credential": "t"})
    app.extensions["google_verifier"] = make_verifier(google_info(name="Asha R."))
    anon.post("/api/auth/google", json={"credential": "t"})
    users = db_rows(app, "SELECT name FROM users")
    assert users == [{"name": "Asha R."}]


def test_invalid_google_token_is_rejected(app, anon):
    app.extensions["google_verifier"] = make_verifier(error=ValueError("bad token"))
    assert anon.post("/api/auth/google", json={"credential": "forged"}).status_code == 401
    assert db_rows(app, "SELECT * FROM users") == []


def test_missing_credential_is_rejected(anon):
    assert anon.post("/api/auth/google", json={}).status_code == 400


def test_unverified_google_email_is_rejected(app, anon):
    app.extensions["google_verifier"] = make_verifier(google_info(email_verified=False))
    assert anon.post("/api/auth/google", json={"credential": "t"}).status_code == 403


def test_only_gmail_accounts_can_sign_in(app, anon):
    app.extensions["google_verifier"] = make_verifier(google_info(email="asha@company.com"))
    response = anon.post("/api/auth/google", json={"credential": "t"})
    assert response.status_code == 403
    assert response.get_json()["error"] == "gmail_required"


def test_domain_restriction_can_be_disabled(tmp_path):
    app = create_app(app_config(tmp_path, ALLOWED_EMAIL_DOMAINS=[]))
    app.extensions["google_verifier"] = make_verifier(google_info(email="asha@company.com"))
    assert Api(app.test_client()).post("/api/auth/google", json={"credential": "t"}).status_code == 200


def test_unauthenticated_requests_get_401(anon):
    for url in ("/api/me", "/api/payments", "/api/events/1/invites"):
        assert anon.get(url).status_code == 401


def test_me_returns_signed_in_customer(api):
    body = api.get("/api/me").get_json()
    assert body["user"]["email"] == "host@gmail.com"
    assert body["events"] == []


def test_logout_ends_session(api):
    assert api.post("/api/auth/logout").status_code == 200
    assert api.get("/api/me").status_code == 401


def test_session_expires_after_ttl(api, clock):
    assert api.get("/api/me").status_code == 200
    clock.advance(days=8)
    assert api.get("/api/me").status_code == 401


def test_forged_session_cookie_is_rejected(app):
    client = app.test_client()
    client.set_cookie("urlovingly_session", "not-a-real-token")
    assert client.get("/api/me").status_code == 401


def test_dev_login_rejects_non_gmail_and_bad_email(anon):
    assert anon.post("/api/auth/dev-login", json={"email": "a@corp.com"}).status_code == 403
    assert anon.post("/api/auth/dev-login", json={"email": "not-an-email"}).status_code == 400


def test_dev_login_hidden_when_disabled(tmp_path):
    app = create_app(app_config(tmp_path, ALLOW_DEV_LOGIN=False))
    assert Api(app.test_client()).post("/api/auth/dev-login", json={"email": "a@gmail.com"}).status_code == 404


def test_production_refuses_insecure_settings(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(app_config(tmp_path, ENV="production", ALLOW_DEV_LOGIN=False))  # mock payments
    with pytest.raises(RuntimeError):
        create_app(app_config(tmp_path, ENV="production", PAYMENT_PROVIDER="razorpay", ALLOW_DEV_LOGIN=True))


def test_production_starts_with_razorpay_configured(tmp_path):
    app = create_app(
        app_config(
            tmp_path, ENV="production", PAYMENT_PROVIDER="razorpay", ALLOW_DEV_LOGIN=False,
            RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="s", SESSION_COOKIE_SECURE=True,
        )
    )
    assert Api(app.test_client()).get("/api/config").get_json()["dev_login"] is False
