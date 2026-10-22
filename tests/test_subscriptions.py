"""Plan selection, payment portal and plan storage (FR-SU-*)."""
import hashlib
import hmac
import json
import sqlite3
import urllib.error
from datetime import datetime, timedelta

import pytest

from server import create_app
from server.payments import RazorpayProvider
from tests.conftest import Api, app_config, create_event, invite_payload, pay, publish


def db_rows(app, sql, params=()):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


# ---- choosing a plan -------------------------------------------------------

def test_free_trial_activates_immediately_and_is_stored(app, api):
    event = create_event(api, "free")
    assert event["status"] == "active"
    assert event["plan"]["id"] == "free"
    assert event["link_limit"] == 5 and event["links_remaining"] == 5
    stored = db_rows(app, "SELECT plan_id, status, user_id FROM events")
    assert stored == [{"plan_id": "free", "status": "active", "user_id": 1}]


def test_free_trial_can_only_be_used_once_per_account(api):
    create_event(api, "free")
    response = api.post("/api/events", json={"plan": "free", "title": "Second"})
    assert response.status_code == 409
    assert response.get_json()["error"] == "trial_already_used"


def test_trial_is_per_account(make_api):
    create_event(make_api("one@gmail.com"), "free")
    assert create_event(make_api("two@gmail.com"), "free")["status"] == "active"


def test_trial_cannot_be_reclaimed_after_upgrading(api):
    event = create_event(api, "free")
    order = api.post(f"/api/events/{event['id']}/upgrade", json={"plan": "standard"}).get_json()
    api.post("/api/payments/mock-confirm", json={"order_id": order["order_id"]})
    assert api.post("/api/events", json={"plan": "free"}).status_code == 409


def test_paid_plan_is_pending_until_paid(api):
    response = api.post("/api/events", json={"plan": "standard", "title": "Wedding"})
    assert response.status_code == 201
    event = response.get_json()["event"]
    assert event["status"] == "pending_payment"
    assert event["features"] == []
    assert publish(api, event).status_code == 402


def test_choosing_same_paid_plan_twice_reuses_pending_event(api):
    first = api.post("/api/events", json={"plan": "grand"}).get_json()["event"]
    second = api.post("/api/events", json={"plan": "grand"})
    assert second.status_code == 200 and second.get_json()["event"]["id"] == first["id"]


@pytest.mark.parametrize("payload", [{}, {"plan": "platinum"}, {"plan": 5}, {"plan": "free", "title": " "}, {"plan": "free", "title": "x" * 121}])
def test_invalid_plan_requests_are_rejected(api, payload):
    assert api.post("/api/events", json=payload).status_code == 400


def test_events_require_sign_in(anon):
    assert anon.post("/api/events", json={"plan": "free"}).status_code == 401


# ---- payment portal --------------------------------------------------------

@pytest.mark.parametrize("plan,paise", [("standard", 99900), ("grand", 249900)])
def test_order_amount_comes_from_server_price(api, plan, paise):
    event = api.post("/api/events", json={"plan": plan}).get_json()["event"]
    order = api.post("/api/payments/order", json={"event_id": event["id"], "amount_paise": 1}).get_json()
    assert order["amount_paise"] == paise
    assert order["currency"] == "INR"


def test_successful_payment_activates_event_and_records_payment(app, api):
    event = create_event(api, "standard", "Wedding")
    assert event["status"] == "active"
    assert "rsvp_dashboard" in event["features"]
    payments = db_rows(app, "SELECT plan_id, amount_paise, status, provider, paid_at FROM payments")
    assert len(payments) == 1
    assert payments[0]["plan_id"] == "standard" and payments[0]["amount_paise"] == 99900
    assert payments[0]["status"] == "paid" and payments[0]["provider"] == "mock" and payments[0]["paid_at"]


def test_payment_confirmation_is_idempotent(app, api):
    event = api.post("/api/events", json={"plan": "standard"}).get_json()["event"]
    order_id = api.post("/api/payments/order", json={"event_id": event["id"]}).get_json()["order_id"]
    first = api.post("/api/payments/mock-confirm", json={"order_id": order_id})
    second = api.post("/api/payments/mock-confirm", json={"order_id": order_id})
    assert first.status_code == second.status_code == 200
    assert len(db_rows(app, "SELECT * FROM payments WHERE status = 'paid'")) == 1


def test_unpaid_order_does_not_activate_event(api):
    event = api.post("/api/events", json={"plan": "standard"}).get_json()["event"]
    api.post("/api/payments/order", json={"event_id": event["id"]})
    assert api.get(f"/api/events/{event['id']}").get_json()["event"]["status"] == "pending_payment"


def test_cannot_order_for_already_active_event(api):
    event = create_event(api, "standard")
    assert api.post("/api/payments/order", json={"event_id": event["id"]}).status_code == 409


def test_cannot_pay_for_or_see_another_customers_event(make_api):
    owner, intruder = make_api("owner@gmail.com"), make_api("intruder@gmail.com")
    event = owner.post("/api/events", json={"plan": "standard"}).get_json()["event"]
    assert intruder.post("/api/payments/order", json={"event_id": event["id"]}).status_code == 404
    order_id = owner.post("/api/payments/order", json={"event_id": event["id"]}).get_json()["order_id"]
    assert intruder.post("/api/payments/mock-confirm", json={"order_id": order_id}).status_code == 404
    assert intruder.get(f"/api/events/{event['id']}").status_code == 404
    assert intruder.get("/api/me").get_json()["events"] == []


def test_payment_history_lists_only_own_payments(make_api):
    owner, other = make_api("owner@gmail.com"), make_api("other@gmail.com")
    create_event(owner, "standard")
    history = owner.get("/api/payments").get_json()["payments"]
    assert len(history) == 1 and history[0]["status"] == "paid"
    assert other.get("/api/payments").get_json()["payments"] == []


# ---- upgrades --------------------------------------------------------------

@pytest.mark.parametrize("start,target,paise", [("free", "standard", 99900), ("free", "grand", 249900), ("standard", "grand", 150000)])
def test_upgrade_charges_price_difference(api, start, target, paise):
    event = create_event(api, start)
    order = api.post(f"/api/events/{event['id']}/upgrade", json={"plan": target}).get_json()
    assert order["amount_paise"] == paise
    api.post("/api/payments/mock-confirm", json={"order_id": order["order_id"]})
    upgraded = api.get(f"/api/events/{event['id']}").get_json()["event"]
    assert upgraded["plan"]["id"] == target and upgraded["status"] == "active"


def test_upgrade_does_not_change_plan_until_paid(api):
    event = create_event(api, "free")
    api.post(f"/api/events/{event['id']}/upgrade", json={"plan": "grand"})
    assert api.get(f"/api/events/{event['id']}").get_json()["event"]["plan"]["id"] == "free"


@pytest.mark.parametrize("start,target", [("standard", "standard"), ("grand", "standard"), ("standard", "free")])
def test_downgrade_or_same_plan_is_rejected(api, start, target):
    event = create_event(api, start)
    assert api.post(f"/api/events/{event['id']}/upgrade", json={"plan": target}).status_code == 400


def test_upgrade_keeps_existing_links_and_extends_hosting(api):
    event = create_event(api, "free")
    invite = publish(api, event).get_json()["invite"]
    assert hosting_period(invite) == timedelta(days=7)
    order = api.post(f"/api/events/{event['id']}/upgrade", json={"plan": "grand"}).get_json()
    api.post("/api/payments/mock-confirm", json={"order_id": order["order_id"]})
    links = api.get(f"/api/events/{event['id']}/invites").get_json()["invites"]
    assert len(links) == 1
    assert hosting_period(links[0]) == timedelta(days=365)


def hosting_period(invite):
    return datetime.fromisoformat(invite["expires_at"]) - datetime.fromisoformat(invite["created_at"])


# ---- Razorpay --------------------------------------------------------------

@pytest.fixture
def razorpay_app(tmp_path, monkeypatch):
    counter = iter(range(1, 100))
    monkeypatch.setattr(RazorpayProvider, "create_order", lambda self, amount, receipt, notes: {"id": f"order_{next(counter)}"})
    return create_app(
        app_config(
            tmp_path, PAYMENT_PROVIDER="razorpay", RAZORPAY_KEY_ID="rzp_test_key",
            RAZORPAY_KEY_SECRET="topsecret", RAZORPAY_WEBHOOK_SECRET="whsecret",
        )
    )


def sign(secret, order_id, payment_id):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def test_razorpay_order_exposes_public_key_only(razorpay_app):
    api = Api(razorpay_app.test_client()).login()
    event = api.post("/api/events", json={"plan": "standard"}).get_json()["event"]
    order = api.post("/api/payments/order", json={"event_id": event["id"]}).get_json()
    assert order["provider"] == "razorpay" and order["key_id"] == "rzp_test_key"
    assert "topsecret" not in json.dumps(order)
    assert api.post("/api/payments/mock-confirm", json={"order_id": order["order_id"]}).status_code == 404


def test_razorpay_valid_signature_activates_event(razorpay_app):
    api = Api(razorpay_app.test_client()).login()
    event = api.post("/api/events", json={"plan": "grand"}).get_json()["event"]
    order_id = api.post("/api/payments/order", json={"event_id": event["id"]}).get_json()["order_id"]
    response = api.post("/api/payments/verify", json={
        "razorpay_order_id": order_id, "razorpay_payment_id": "pay_1",
        "razorpay_signature": sign("topsecret", order_id, "pay_1"),
    })
    assert response.status_code == 200 and response.get_json()["event"]["status"] == "active"
    assert db_rows(razorpay_app, "SELECT provider_payment_id FROM payments")[0]["provider_payment_id"] == "pay_1"


def test_razorpay_forged_signature_is_rejected(razorpay_app):
    api = Api(razorpay_app.test_client()).login()
    event = api.post("/api/events", json={"plan": "grand"}).get_json()["event"]
    order_id = api.post("/api/payments/order", json={"event_id": event["id"]}).get_json()["order_id"]
    response = api.post("/api/payments/verify", json={
        "razorpay_order_id": order_id, "razorpay_payment_id": "pay_1", "razorpay_signature": "0" * 64,
    })
    assert response.status_code == 400
    assert api.get(f"/api/events/{event['id']}").get_json()["event"]["status"] == "pending_payment"


def test_razorpay_verify_requires_all_fields(razorpay_app):
    api = Api(razorpay_app.test_client()).login()
    assert api.post("/api/payments/verify", json={"razorpay_order_id": "o"}).status_code == 400


def test_razorpay_signature_cannot_be_used_by_another_account(razorpay_app):
    owner = Api(razorpay_app.test_client()).login("owner@gmail.com")
    thief = Api(razorpay_app.test_client()).login("thief@gmail.com")
    event = owner.post("/api/events", json={"plan": "standard"}).get_json()["event"]
    order_id = owner.post("/api/payments/order", json={"event_id": event["id"]}).get_json()["order_id"]
    response = thief.post("/api/payments/verify", json={
        "razorpay_order_id": order_id, "razorpay_payment_id": "pay_1",
        "razorpay_signature": sign("topsecret", order_id, "pay_1"),
    })
    assert response.status_code == 404


def webhook_body(order_id, amount, event="payment.captured"):
    return json.dumps({"event": event, "payload": {"payment": {"entity": {"id": "pay_w", "order_id": order_id, "amount": amount}}}}).encode()


def post_webhook(client, body, secret="whsecret"):
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/api/payments/razorpay/webhook", data=body, headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"})


def test_webhook_activates_event_without_browser_callback(razorpay_app):
    api = Api(razorpay_app.test_client()).login()
    event = api.post("/api/events", json={"plan": "standard"}).get_json()["event"]
    order_id = api.post("/api/payments/order", json={"event_id": event["id"]}).get_json()["order_id"]
    assert post_webhook(razorpay_app.test_client(), webhook_body(order_id, 99900)).status_code == 200
    assert api.get(f"/api/events/{event['id']}").get_json()["event"]["status"] == "active"


def test_webhook_with_bad_signature_is_rejected(razorpay_app):
    api = Api(razorpay_app.test_client()).login()
    event = api.post("/api/events", json={"plan": "standard"}).get_json()["event"]
    order_id = api.post("/api/payments/order", json={"event_id": event["id"]}).get_json()["order_id"]
    assert post_webhook(razorpay_app.test_client(), webhook_body(order_id, 99900), secret="wrong").status_code == 400
    assert api.get(f"/api/events/{event['id']}").get_json()["event"]["status"] == "pending_payment"


def test_webhook_with_wrong_amount_does_not_activate(razorpay_app):
    api = Api(razorpay_app.test_client()).login()
    event = api.post("/api/events", json={"plan": "standard"}).get_json()["event"]
    order_id = api.post("/api/payments/order", json={"event_id": event["id"]}).get_json()["order_id"]
    post_webhook(razorpay_app.test_client(), webhook_body(order_id, 100))
    assert api.get(f"/api/events/{event['id']}").get_json()["event"]["status"] == "pending_payment"


def test_gateway_outage_returns_502(tmp_path, monkeypatch):
    def boom(self, amount, receipt, notes):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(RazorpayProvider, "create_order", boom)
    app = create_app(app_config(tmp_path, PAYMENT_PROVIDER="razorpay", RAZORPAY_KEY_ID="k", RAZORPAY_KEY_SECRET="s"))
    api = Api(app.test_client()).login()
    event = api.post("/api/events", json={"plan": "standard"}).get_json()["event"]
    assert api.post("/api/payments/order", json={"event_id": event["id"]}).status_code == 502


def test_razorpay_provider_builds_authenticated_order_request(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"id": "order_live"}'

    def fake_urlopen(request, timeout):
        captured["url"], captured["body"], captured["auth"] = request.full_url, json.loads(request.data), request.headers["Authorization"]
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    order = RazorpayProvider("kid", "ksecret").create_order(99900, "rcpt", {"a": "b"})
    assert order["id"] == "order_live"
    assert captured["url"] == "https://api.razorpay.com/v1/orders"
    assert captured["body"]["amount"] == 99900 and captured["body"]["currency"] == "INR"
    assert captured["auth"].startswith("Basic ")
