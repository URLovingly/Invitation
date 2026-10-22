"""Landing page, login-gated studio and web security (FR-LP-*, FR-ST-*, NFR-SEC-*)."""
import os
import re

import pytest

from server.config import BASE_DIR
from server.plans import PLANS
from tests.conftest import create_event, publish


def read(*parts):
    with open(os.path.join(BASE_DIR, *parts), encoding="utf-8") as handle:
        return handle.read()


# ---- landing page ----------------------------------------------------------

def test_landing_page_is_public(anon):
    response = anon.get("/")
    assert response.status_code == 200 and b"URLovingly" in response.data


def test_landing_page_explains_product_and_uniqueness():
    html = read("index.html")
    for anchor in ('id="features"', 'id="unique"', 'id="how-it-works"', 'id="pricing"', 'id="payment"'):
        assert anchor in html
    for phrase in ("scratch", "personalized", "WhatsApp", "RSVP", "UPI Shagun", "multi-day", "background audio"):
        assert phrase.lower() in html.lower(), phrase


def test_landing_page_offers_free_trial_and_all_three_plans():
    html = read("index.html")
    assert "Start free trial" in html
    for plan in PLANS.values():
        assert f'data-plan="{plan["id"]}"' in html, plan["id"]
        assert plan["name"] in html
        assert f"Up to {plan['link_limit']} personalized guest links" in html
        for label in plan["highlights"]:
            assert label in html, label
        if plan["price_paise"]:
            assert f"\u20b9{plan['price_paise'] // 100:,}" in html


def test_landing_page_contains_payment_portal_and_google_login():
    html = read("index.html")
    assert 'id="checkoutModal"' in html
    assert "accounts.google.com/gsi/client" in html
    assert "/api/auth/google" in html and "/api/payments/order" in html


def test_github_pages_logo_and_google_chooser_fallback():
    html = read("index.html")
    assert os.path.isfile(os.path.join(BASE_DIR, "URLovingly_Icon.jpg"))
    assert html.count('src="./URLovingly_Icon.jpg"') == 2
    assert 'href="./URLovingly_Icon.jpg"' in html
    assert '<a href="./" class="flex items-center gap-3">' in html
    assert 'name="google-client-id"' in html
    assert "requestAnimationFrame(() => renderGoogleButton())" in html
    assert "Google account selection is available, but sign-in needs the URLovingly application backend." in html
    assert "GitHub Pages only hosts static files." in html
    assert "Authorized JavaScript origins" in html


def test_landing_hero_previews_the_royal_template():
    html = read("index.html")
    assert "By royal invitation" in html and 'class="rp-card"' in html


def test_landing_page_never_ships_secrets():
    html = read("index.html")
    assert not re.search(r"rzp_(live|test)_\w{6,}", html)
    assert "key_secret" not in html.lower()


# ---- studio is only available after login ----------------------------------

def test_studio_redirects_anonymous_visitors_to_landing(anon):
    response = anon.get("/studio")
    assert response.status_code == 302 and "/?signin=1" in response.headers["Location"]


def test_studio_redirects_signed_in_user_without_plan_to_pricing(api):
    response = api.get("/studio")
    assert response.status_code == 302 and "choose=plan" in response.headers["Location"]


def test_studio_redirects_when_only_unpaid_event_exists(api):
    api.post("/api/events", json={"plan": "standard"})
    assert api.get("/studio").status_code == 302


def test_studio_is_served_once_plan_is_active(api):
    create_event(api, "free")
    response = api.get("/studio")
    assert response.status_code == 200 and b"Create Bespoke Event Invitations" in response.data
    assert response.headers["Cache-Control"] == "no-store"


def test_studio_source_is_not_publicly_reachable(anon):
    for path in ("/private/studio.html", "/studio.html", "/schema.sql", "/server/auth.py", "/data/urlovingly.db"):
        assert anon.get(path).status_code == 404


def test_studio_has_no_embedded_login_wall_and_talks_to_local_api():
    html = read("private", "studio.html")
    assert 'id="loginSection"' not in html
    assert "workers.dev" not in html and "github.io" not in html
    assert "/api/me" in html and "/api/events/" in html


def test_studio_marks_every_paid_feature_for_plan_gating():
    html = read("private", "studio.html")
    for feature in ("whatsapp_generator", "rsvp_dashboard", "multi_day_routing", "upi_shagun", "custom_audio"):
        assert f'data-feature="{feature}"' in html, feature


def test_invitation_templates_require_login(anon, api):
    assert anon.get("/templates/royal/index.html").status_code == 401
    create_event(api, "free")
    assert api.get("/templates/royal/index.html").status_code == 200
    assert api.get("/templates/nope/index.html").status_code == 404


# ---- security --------------------------------------------------------------

def test_state_changing_api_calls_need_csrf_header(app, api):
    raw = app.test_client()
    api.login()
    raw.set_cookie("urlovingly_session", api.client.get_cookie("urlovingly_session").value)
    assert raw.post("/api/events", json={"plan": "free"}).status_code == 403
    assert raw.post("/api/events", json={"plan": "free"}, headers={"X-Requested-With": "urlovingly"}).status_code == 201


def test_login_requires_csrf_header(app):
    assert app.test_client().post("/api/auth/dev-login", json={"email": "a@gmail.com"}).status_code == 403


def test_unknown_api_routes_return_json(anon):
    response = anon.get("/api/nothing")
    assert response.status_code == 404 and response.is_json


def test_security_headers_present(anon):
    assert anon.get("/api/plans").headers["X-Content-Type-Options"] == "nosniff"


def test_sql_injection_in_names_is_harmless(api, app):
    event = create_event(api, "free")
    assert publish(api, event, name="x'); DROP TABLE invites;--").status_code == 201
    assert api.get(f"/api/events/{event['id']}/invites").status_code == 200


def test_path_traversal_in_slugs_is_not_served(anon):
    assert anon.get("/..%2F..%2Fetc/to/passwd/").status_code == 404
