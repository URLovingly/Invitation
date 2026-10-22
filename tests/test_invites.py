"""Guest links: quotas, slugs, hosting period and serving (FR-IN-*)."""
from datetime import timedelta

import pytest

from tests.conftest import create_event, invite_payload, publish


def test_publish_returns_personalized_url_and_counts_link(api):
    event = create_event(api, "free")
    response = publish(api, event, name="Rahul Sharma & Family", couple="Aarav & Priya")
    assert response.status_code == 201
    body = response.get_json()
    assert body["invite"]["url"].endswith("/aarav-and-priya/to/rahul-sharma-and-family/")
    assert body["event"]["links_used"] == 1 and body["event"]["links_remaining"] == 4


def test_published_link_serves_the_invitation(api):
    event = create_event(api, "free")
    publish(api, event)
    page = api.get("/aarav-and-priya/to/rahul-sharma/")
    assert page.status_code == 200
    assert b"Hello Rahul Sharma" in page.data


def test_published_link_is_public_without_login(app, api):
    event = create_event(api, "free")
    publish(api, event)
    guest = app.test_client().get("/aarav-and-priya/to/rahul-sharma/")
    assert guest.status_code == 200


def test_unknown_link_returns_404(anon):
    assert anon.get("/nobody/to/nothing/").status_code == 404


def test_invite_is_stored_with_owner_and_event(api):
    event = create_event(api, "free")
    publish(api, event)
    listed = api.get(f"/api/events/{event['id']}/invites").get_json()["invites"]
    assert [i["guest_name"] for i in listed] == ["Rahul Sharma"]
    assert listed[0]["template"] == "royal" and listed[0]["couple_names"] == "Aarav & Priya"


@pytest.mark.parametrize("plan,limit", [("free", 5), ("standard", 100)])
def test_link_limit_is_enforced_per_plan(api, plan, limit):
    event = create_event(api, plan)
    for number in range(limit):
        assert publish(api, event, name=f"Guest {number}").status_code == 201
    blocked = publish(api, event, name="One Too Many")
    assert blocked.status_code == 403
    assert blocked.get_json()["error"] == "link_limit_reached" and blocked.get_json()["limit"] == limit
    assert api.get(f"/api/events/{event['id']}").get_json()["event"]["links_used"] == limit


def test_grand_plan_allows_up_to_500_links(app, api):
    event = create_event(api, "grand")
    assert event["link_limit"] == 500
    # Fill to the limit directly in the database to keep the test fast, then check the boundary via the API.
    import sqlite3

    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        conn.executemany(
            """INSERT INTO invites (public_id, event_id, user_id, host_email, guest_name, couple_names,
                   couple_slug, guest_slug, template, html, created_at, updated_at, expires_at)
               VALUES (?, ?, 1, 'host@gmail.com', 'g', 'c', 'c', ?, 'royal', '<p></p>', 'x', 'x', '2999-01-01T00:00:00+00:00')""",
            [(f"pub{n}", event["id"], f"g{n}") for n in range(499)],
        )
        conn.commit()
    finally:
        conn.close()
    assert publish(api, event, name="Number 500").status_code == 201
    assert publish(api, event, name="Number 501").status_code == 403


def test_republishing_same_guest_updates_without_using_quota(api):
    event = create_event(api, "free")
    first = publish(api, event, name="Rahul")
    again = publish(api, event, name="Rahul", rendered_html="<html><body>Updated</body></html>")
    assert first.status_code == 201 and again.status_code == 200
    assert again.get_json()["invite"]["id"] == first.get_json()["invite"]["id"]
    assert again.get_json()["event"]["links_used"] == 1
    assert b"Updated" in api.get("/aarav-and-priya/to/rahul/").data


def test_link_owned_by_another_customer_cannot_be_overwritten(make_api):
    owner, other = make_api("owner@gmail.com"), make_api("other@gmail.com")
    owner_event, other_event = create_event(owner, "free"), create_event(other, "free")
    publish(owner, owner_event, name="Rahul", rendered_html="<html><body>Owner page</body></html>")
    clash = publish(other, other_event, name="Rahul", rendered_html="<html><body>Hijacked</body></html>")
    assert clash.status_code == 409 and clash.get_json()["error"] == "slug_taken"
    assert b"Owner page" in owner.get("/aarav-and-priya/to/rahul/").data


def test_customer_cannot_publish_to_someone_elses_event(make_api):
    owner, other = make_api("owner@gmail.com"), make_api("other@gmail.com")
    event = create_event(owner, "free")
    assert publish(other, event).status_code == 404
    assert other.get(f"/api/events/{event['id']}/invites").status_code == 404


@pytest.mark.parametrize(
    "override",
    [
        {"name": ""},
        {"name": "x" * 101},
        {"couple_names": " "},
        {"template": "../../etc/passwd"},
        {"template": "does-not-exist"},
        {"rendered_html": ""},
        {"rendered_html": "x" * (400 * 1024 + 1)},
        {"allowed_ceremonies": "haldi"},
    ],
)
def test_invalid_invite_payloads_are_rejected(api, override):
    event = create_event(api, "free")
    response = api.post(f"/api/events/{event['id']}/invites", json=invite_payload(**override))
    assert response.status_code == 400


def test_all_bundled_templates_are_accepted(api):
    event = create_event(api, "standard")
    for number, template in enumerate(
        ["heritage-temple-art", "modern-minimalist", "regal-palatial", "royal", "tropical-destination", "urlovingly", "vibrant-contemporary", "vintage-nostalgia"]
    ):
        assert publish(api, event, name=f"G{number}", template=template).status_code == 201


def test_non_ascii_names_still_get_a_usable_slug(api):
    event = create_event(api, "free")
    body = publish(api, event, name="राहुल", couple="आरव").get_json()
    assert body["invite"]["url"].endswith("/event/to/guest/")


# ---- hosting period --------------------------------------------------------

@pytest.mark.parametrize("plan,days", [("free", 7), ("standard", 180), ("grand", 365)])
def test_link_is_hosted_for_plan_period_then_expires(api, clock, plan, days):
    event = create_event(api, plan)
    publish(api, event)
    clock.advance(days=days - 1)
    assert api.get("/aarav-and-priya/to/rahul-sharma/").status_code == 200
    clock.advance(days=2)
    expired = api.get("/aarav-and-priya/to/rahul-sharma/")
    assert expired.status_code == 410 and b"expired" in expired.data.lower()


def test_expired_links_are_flagged_in_dashboard(api, clock):
    event = create_event(api, "free")
    publish(api, event)
    clock.advance(days=8)
    api.login()  # the 7-day session has lapsed as well
    assert api.get(f"/api/events/{event['id']}/invites").get_json()["invites"][0]["expired"] is True


# ---- safety of customer-supplied markup ------------------------------------

def test_invitation_pages_are_sandboxed(api):
    event = create_event(api, "free")
    publish(api, event, rendered_html="<html><body><script>fetch('/api/me')</script></body></html>")
    csp = api.get("/aarav-and-priya/to/rahul-sharma/").headers["Content-Security-Policy"]
    assert csp.startswith("sandbox") and "allow-scripts" in csp
    assert "allow-same-origin" not in csp
