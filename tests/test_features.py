"""Plan-gated features: WhatsApp, RSVP, routing, UPI Shagun, audio (FR-WA/RS/MD/UP/AD-*)."""
import io

import pytest

from tests.conftest import create_event, invite_payload, publish

MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 64
FEATURE_PLANS = {
    "whatsapp_generator": {"standard", "grand"},
    "rsvp_dashboard": {"standard", "grand"},
    "multi_day_routing": {"grand"},
    "upi_shagun": {"grand"},
    "custom_audio": {"grand"},
}


def feature_requests(api, event):
    eid = event["id"]
    return {
        "whatsapp_generator": lambda: api.post(f"/api/events/{eid}/whatsapp", json={}),
        "rsvp_dashboard": lambda: api.get(f"/api/events/{eid}/rsvps"),
        "multi_day_routing": lambda: publish(api, event, name="Routed", allowed_ceremonies=["Haldi"]),
        "upi_shagun": lambda: api.put(f"/api/events/{eid}/settings", json={"upi_id": "host@okbank"}),
        "custom_audio": lambda: api.post(f"/api/events/{eid}/audio", data={"audio": (io.BytesIO(MP3), "song.mp3")}, headers={"X-Requested-With": "urlovingly"}),
    }


# ---- the plan decides what the customer can use ----------------------------

@pytest.mark.parametrize("plan", ["free", "standard", "grand"])
def test_event_lists_exactly_the_features_of_its_plan(api, plan):
    event = create_event(api, plan)
    expected = {f for f, plans in FEATURE_PLANS.items() if plan in plans}
    assert set(event["features"]) == expected


@pytest.mark.parametrize("plan", ["free", "standard", "grand"])
@pytest.mark.parametrize("feature", list(FEATURE_PLANS))
def test_feature_endpoints_follow_plan_entitlements(api, plan, feature):
    event = create_event(api, plan)
    response = feature_requests(api, event)[feature]()
    if plan in FEATURE_PLANS[feature]:
        assert response.status_code in (200, 201), response.get_json()
    else:
        assert response.status_code == 403
        assert response.get_json()["error"] == "feature_not_in_plan"
        assert response.get_json()["feature"] == feature
        assert response.get_json()["required_plan"] in FEATURE_PLANS[feature]


def test_features_are_unavailable_until_payment_completes(api):
    event = api.post("/api/events", json={"plan": "grand"}).get_json()["event"]
    assert api.post(f"/api/events/{event['id']}/whatsapp", json={}).status_code == 402
    assert api.get(f"/api/events/{event['id']}/rsvps").status_code == 402


# ---- WhatsApp message generator --------------------------------------------

def test_whatsapp_generator_builds_personal_message_and_link(api):
    event = create_event(api, "standard")
    publish(api, event, name="Rahul Sharma", guest_phone="98765 43210")
    publish(api, event, name="Meera", guest_phone="")
    body = api.post(f"/api/events/{event['id']}/whatsapp", json={}).get_json()
    first, second = body["messages"]
    assert "Rahul Sharma" in first["message"] and "/aarav-and-priya/to/rahul-sharma/" in first["message"]
    assert first["phone"] == "919876543210"
    assert first["url"].startswith("https://wa.me/919876543210?text=")
    assert second["url"].startswith("https://wa.me/?text=")


def test_whatsapp_generator_supports_custom_template(api):
    event = create_event(api, "standard")
    publish(api, event, name="Rahul")
    body = api.post(f"/api/events/{event['id']}/whatsapp", json={"template": "Namaste {guest_name}! {link} {unknown}"}).get_json()
    assert body["messages"][0]["message"].startswith("Namaste Rahul! http")
    assert body["messages"][0]["message"].endswith("{unknown}")


def test_whatsapp_generator_rejects_oversized_template(api):
    event = create_event(api, "standard")
    assert api.post(f"/api/events/{event['id']}/whatsapp", json={"template": "x" * 1001}).status_code == 400


def test_guest_phone_is_ignored_on_free_plan(api):
    event = create_event(api, "free")
    body = publish(api, event, guest_phone="9876543210").get_json()
    assert body["invite"]["guest_phone"] == ""


# ---- RSVP ------------------------------------------------------------------

def public_rsvp_endpoint(app, html):
    import re

    return re.search(r"var endpoint = \"([^\"]+)\"", html).group(1)


def test_invitation_includes_rsvp_widget_only_on_paid_plans(api):
    free_event = create_event(api, "free")
    publish(api, free_event, name="A")
    assert b"ul-rsvp" not in api.get("/aarav-and-priya/to/a/").data


def test_guest_can_rsvp_and_host_sees_it_live(app, api):
    event = create_event(api, "standard")
    publish(api, event, name="Rahul")
    publish(api, event, name="Meera")
    page = api.get("/aarav-and-priya/to/rahul/").get_data(as_text=True)
    assert "ul-rsvp" in page
    endpoint = public_rsvp_endpoint(app, page).replace("http://localhost", "")

    guest = app.test_client()  # no cookies, no CSRF header: a plain guest
    response = guest.post(endpoint, json={"response": "yes", "guests": 3, "message": "Congrats!"})
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"

    dashboard = api.get(f"/api/events/{event['id']}/rsvps").get_json()
    assert dashboard["summary"] == {"yes": 1, "no": 0, "maybe": 0, "pending": 1, "attending_guests": 3}
    rahul = next(i for i in dashboard["items"] if i["guest_name"] == "Rahul")
    assert rahul["response"] == "yes" and rahul["guests"] == 3 and rahul["message"] == "Congrats!"


def test_guest_can_change_their_rsvp(app, api):
    event = create_event(api, "standard")
    publish(api, event, name="Rahul")
    endpoint = public_rsvp_endpoint(app, api.get("/aarav-and-priya/to/rahul/").get_data(as_text=True)).replace("http://localhost", "")
    guest = app.test_client()
    guest.post(endpoint, json={"response": "yes", "guests": 2})
    guest.post(endpoint, json={"response": "no", "guests": 1})
    summary = api.get(f"/api/events/{event['id']}/rsvps").get_json()["summary"]
    assert summary["no"] == 1 and summary["yes"] == 0 and summary["attending_guests"] == 0


@pytest.mark.parametrize("body", [{"response": "definitely"}, {"response": "yes", "guests": 0}, {"response": "yes", "guests": 21},
                                  {"response": "yes", "guests": True}, {"response": "yes", "guests": "2"}, {"response": "yes", "message": "x" * 301}, {}])
def test_invalid_rsvp_is_rejected(app, api, body):
    event = create_event(api, "standard")
    publish(api, event, name="Rahul")
    endpoint = public_rsvp_endpoint(app, api.get("/aarav-and-priya/to/rahul/").get_data(as_text=True)).replace("http://localhost", "")
    assert app.test_client().post(endpoint, json=body).status_code == 400


def test_rsvp_to_unknown_invitation_is_404(app):
    assert app.test_client().post("/api/rsvp/doesnotexist", json={"response": "yes"}).status_code == 404


def test_rsvp_endpoint_answers_cors_preflight(app):
    response = app.test_client().options("/api/rsvp/anything")
    assert response.status_code == 204 and response.headers["Access-Control-Allow-Origin"] == "*"


def test_rsvp_is_closed_after_hosting_expires(app, api, clock):
    event = create_event(api, "standard")
    publish(api, event, name="Rahul")
    endpoint = public_rsvp_endpoint(app, api.get("/aarav-and-priya/to/rahul/").get_data(as_text=True)).replace("http://localhost", "")
    clock.advance(days=181)
    assert app.test_client().post(endpoint, json={"response": "yes"}).status_code == 404


def test_rsvp_dashboard_is_private_to_the_host(make_api):
    owner, other = make_api("owner@gmail.com"), make_api("other@gmail.com")
    event = create_event(owner, "standard")
    assert other.get(f"/api/events/{event['id']}/rsvps").status_code == 404


# ---- multi-day selective event routing -------------------------------------

def test_grand_plan_stores_selected_ceremonies_per_guest(api):
    event = create_event(api, "grand")
    body = publish(api, event, name="Uncle", allowed_ceremonies=["Haldi Ceremony", "Wedding Reception / Valima"]).get_json()
    assert body["invite"]["allowed_ceremonies"] == ["Haldi Ceremony", "Wedding Reception / Valima"]
    listed = api.get(f"/api/events/{event['id']}/invites").get_json()["invites"]
    assert listed[0]["allowed_ceremonies"] == ["Haldi Ceremony", "Wedding Reception / Valima"]


def test_standard_plan_cannot_route_ceremonies_but_can_publish_without(api):
    event = create_event(api, "standard")
    assert publish(api, event, name="A", allowed_ceremonies=["Haldi"]).status_code == 403
    assert publish(api, event, name="B", allowed_ceremonies=[]).status_code == 201
    assert api.get(f"/api/events/{event['id']}").get_json()["event"]["links_used"] == 1


# ---- UPI Shagun ------------------------------------------------------------

def test_upi_shagun_block_appears_on_grand_invitations(api):
    event = create_event(api, "grand")
    publish(api, event, name="Rahul")
    assert b"ul-upi" not in api.get("/aarav-and-priya/to/rahul/").data
    assert api.put(f"/api/events/{event['id']}/settings", json={"upi_id": "priya@okhdfc", "upi_name": "Priya Sharma"}).status_code == 200
    page = api.get("/aarav-and-priya/to/rahul/").get_data(as_text=True)
    assert "upi://pay?pa=priya@okhdfc&amp;pn=Priya%20Sharma&amp;cu=INR" in page
    assert "priya@okhdfc" in page


@pytest.mark.parametrize("upi", ["no-at-sign", "a@b", "bad id@bank", "x@bank<script>", "@bank"])
def test_invalid_upi_ids_are_rejected(api, upi):
    event = create_event(api, "grand")
    assert api.put(f"/api/events/{event['id']}/settings", json={"upi_id": upi}).status_code == 400


def test_upi_details_are_html_escaped(api):
    event = create_event(api, "grand")
    publish(api, event, name="Rahul")
    api.put(f"/api/events/{event['id']}/settings", json={"upi_id": "host@okbank", "upi_name": "<script>alert(1)</script>"})
    page = api.get("/aarav-and-priya/to/rahul/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page


def test_upi_can_be_cleared(api):
    event = create_event(api, "grand")
    publish(api, event, name="Rahul")
    api.put(f"/api/events/{event['id']}/settings", json={"upi_id": "host@okbank"})
    api.put(f"/api/events/{event['id']}/settings", json={"upi_id": ""})
    assert b"ul-upi" not in api.get("/aarav-and-priya/to/rahul/").data


# ---- custom background audio -----------------------------------------------

def upload(api, event, content=MP3, filename="song.mp3"):
    return api.post(f"/api/events/{event['id']}/audio", data={"audio": (io.BytesIO(content), filename)}, headers={"X-Requested-With": "urlovingly"})


def test_audio_upload_is_embedded_and_streamed(app, api):
    event = create_event(api, "grand")
    publish(api, event, name="Rahul")
    body = upload(api, event).get_json()["event"]
    assert body["audio_url"].startswith("/media/audio/")
    page = api.get("/aarav-and-priya/to/rahul/").get_data(as_text=True)
    assert "ul-audio" in page and body["audio_url"] in page
    served = app.test_client().get(body["audio_url"])
    assert served.status_code == 200 and served.mimetype == "audio/mpeg" and served.data == MP3


def test_audio_is_not_embedded_without_upload(api):
    event = create_event(api, "grand")
    publish(api, event, name="Rahul")
    assert b"ul-audio" not in api.get("/aarav-and-priya/to/rahul/").data


@pytest.mark.parametrize("content,name", [(b"<html>not audio</html>", "song.mp3"), (b"MZ\x90\x00 exe", "song.mp3"), (b"", "empty.mp3")])
def test_non_audio_uploads_are_rejected_regardless_of_extension(api, content, name):
    event = create_event(api, "grand")
    assert upload(api, event, content, name).status_code == 400


def test_oversized_audio_is_rejected(api):
    event = create_event(api, "grand")
    assert upload(api, event, MP3 + b"\x00" * (3 * 1024 * 1024)).status_code == 413


def test_audio_upload_requires_file_field(api):
    event = create_event(api, "grand")
    assert api.post(f"/api/events/{event['id']}/audio", data={}, headers={"X-Requested-With": "urlovingly"}).status_code == 400


def test_audio_can_be_removed(app, api):
    event = create_event(api, "grand")
    url = upload(api, event).get_json()["event"]["audio_url"]
    assert api.delete(f"/api/events/{event['id']}/audio").get_json()["event"]["audio_url"] == ""
    assert app.test_client().get(url).status_code == 404


def test_audio_stream_is_public_but_unknown_media_is_404(app, api):
    event = create_event(api, "grand")
    url = upload(api, event).get_json()["event"]["audio_url"]
    assert app.test_client().get(url).status_code == 200
    assert app.test_client().get("/media/audio/unknown").status_code == 404
