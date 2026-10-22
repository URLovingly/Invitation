"""Owner-only account and stored-asset dashboard tests."""
import json
import os

from server.db import get_db
from tests.conftest import create_event, publish


def mark_google_authenticated(app, email):
    with app.app_context():
        get_db().execute("UPDATE users SET google_sub = ? WHERE email = ?", ("verified-google-subject", email))


def test_owner_dashboard_is_disabled_without_configured_owner(app, api):
    create_event(api, "free")
    app.config["OWNER_EMAIL"] = ""
    assert api.get("/owner").status_code == 404
    assert api.get("/api/owner/overview").status_code == 404


def test_owner_dashboard_requires_exact_google_owner(app, make_api):
    app.config["OWNER_EMAIL"] = "owner@gmail.com"
    other = make_api("other@gmail.com")
    mark_google_authenticated(app, "other@gmail.com")
    assert other.get("/owner").status_code == 404
    assert other.get("/api/owner/overview").status_code == 404

    dev_only_owner = make_api("owner@gmail.com")
    assert dev_only_owner.get("/owner").status_code == 404
    mark_google_authenticated(app, "owner@gmail.com")
    assert dev_only_owner.get("/owner").status_code == 200


def test_owner_overview_shows_links_and_asset_metadata_only(app, make_api):
    app.config["OWNER_EMAIL"] = "owner@gmail.com"
    owner = make_api("owner@gmail.com")
    mark_google_authenticated(app, "owner@gmail.com")
    event = create_event(owner, "free")
    publish(
        owner,
        event,
        guest_phone="9876543210",
        custom_note="PRIVATE PERSONAL NOTE",
        rendered_html='<html><body><img src="data:image/png;base64,AAAA">SECRET INVITATION BODY</body></html>',
    )

    filename = f"{event['public_id']}.mp3"
    audio_dir = os.path.join(app.config["MEDIA_DIR"], "audio")
    os.makedirs(audio_dir, exist_ok=True)
    with open(os.path.join(audio_dir, filename), "wb") as audio:
        audio.write(b"ID3sample")
    with app.app_context():
        get_db().execute(
            "UPDATE events SET audio_file = ?, audio_type = ? WHERE id = ?",
            (filename, "audio/mpeg", event["id"]),
        )

    page = owner.get("/owner")
    response = owner.get("/api/owner/overview")
    assert page.status_code == 200
    assert page.headers["Cache-Control"].startswith("private, no-store")
    assert page.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
    assert page.headers["X-Frame-Options"] == "DENY"
    assert response.status_code == 200
    assert response.headers["Cache-Control"].startswith("private, no-store")

    payload = response.get_json()
    assert payload["summary"]["customer_count"] == 1
    assert payload["summary"]["event_count"] == 1
    assert payload["summary"]["link_count"] == 1
    assert payload["summary"]["stored_bytes"] > 0
    customer = payload["customers"][0]
    assert customer["email"] == "owner@gmail.com"
    dashboard_event = customer["events"][0]
    assert dashboard_event["links"][0]["url"] == "/aarav-and-priya/to/rahul-sharma/"
    assert dashboard_event["links"][0]["embedded_photo_count"] == 1
    assert dashboard_event["assets"][0]["name"] == filename
    assert dashboard_event["assets"][0]["size_bytes"] == len(b"ID3sample")
    serialized = json.dumps(payload)
    for private_value in ("9876543210", "PRIVATE PERSONAL NOTE", "SECRET INVITATION BODY"):
        assert private_value not in serialized


def test_owner_routes_require_a_session(anon):
    assert anon.get("/private/owner.html").status_code == 404
    page = anon.get("/owner")
    assert page.status_code == 302 and "/?signin=1" in page.headers["Location"]
    response = anon.get("/api/owner/overview")
    assert response.status_code == 401 and response.is_json