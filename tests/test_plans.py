"""Plans, pricing and the public configuration (FR-PL-*)."""
import sqlite3

from server.plans import PLANS


def test_three_plans_are_offered_in_order(anon):
    plans = anon.get("/api/plans").get_json()["plans"]
    assert [p["id"] for p in plans] == ["free", "standard", "grand"]


def test_free_plan_definition(anon):
    free = {p["id"]: p for p in anon.get("/api/plans").get_json()["plans"]}["free"]
    assert free["name"] == "Free Tier (Trial)"
    assert free["price_rupees"] == 0
    assert free["link_limit"] == 5
    assert free["features"] == []


def test_standard_plan_definition(anon):
    standard = {p["id"]: p for p in anon.get("/api/plans").get_json()["plans"]}["standard"]
    assert standard["name"] == "Standard Celebration"
    assert standard["price_rupees"] == 999 and standard["price_paise"] == 99900
    assert standard["link_limit"] == 100
    assert standard["hosting_days"] == 180
    assert set(standard["features"]) == {"whatsapp_generator", "rsvp_dashboard"}


def test_grand_plan_definition(anon):
    grand = {p["id"]: p for p in anon.get("/api/plans").get_json()["plans"]}["grand"]
    assert grand["name"] == "Grand Celebration"
    assert grand["price_rupees"] == 2499 and grand["price_paise"] == 249900
    assert grand["link_limit"] == 500
    assert grand["hosting_days"] == 365
    assert set(grand["features"]) == {
        "whatsapp_generator", "rsvp_dashboard", "multi_day_routing", "upi_shagun", "custom_audio",
    }


def test_plans_endpoint_is_public_and_labels_features(anon):
    body = anon.get("/api/plans").get_json()
    assert set(body["feature_labels"]) == set(PLANS["grand"]["features"])


def test_plans_are_stored_in_database(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        rows = {r[0]: r for r in conn.execute("SELECT id, price_paise, link_limit, hosting_days FROM plans")}
    finally:
        conn.close()
    assert rows["free"][1:] == (0, 5, 7)
    assert rows["standard"][1:] == (99900, 100, 180)
    assert rows["grand"][1:] == (249900, 500, 365)


def test_public_config_exposes_no_secrets(anon):
    body = anon.get("/api/config").get_json()
    assert set(body) == {"google_client_id", "dev_login", "payment_provider", "razorpay_key_id"}
    assert body["payment_provider"] == "mock"
