import base64
import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.request

from flask import Blueprint, current_app, jsonify, request

from . import util
from .auth import current_user, login_required
from .db import get_db, tx
from .errors import api_error
from .models import event_dict, get_event_for_user, invite_expiry, upgrade_price
from .plans import get_plan, public_plan

bp = Blueprint("payments", __name__)


class MockProvider:
    """Development-only provider: orders are confirmed by the server without a card."""

    name = "mock"

    def create_order(self, amount_paise, receipt, notes):
        return {"id": f"mock_order_{secrets.token_hex(8)}"}


class RazorpayProvider:
    name = "razorpay"
    ORDERS_URL = "https://api.razorpay.com/v1/orders"

    def __init__(self, key_id, key_secret):
        self.key_id = key_id
        self.key_secret = key_secret

    def create_order(self, amount_paise, receipt, notes):
        body = json.dumps({"amount": amount_paise, "currency": "INR", "receipt": receipt, "notes": notes}).encode()
        credentials = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode()).decode()
        req = urllib.request.Request(
            self.ORDERS_URL,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Basic {credentials}"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read())

    def verify_signature(self, order_id, payment_id, signature):
        expected = hmac.new(self.key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")


def verify_webhook_signature(secret, body, signature):
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def build_provider(config):
    if config["PAYMENT_PROVIDER"] == "razorpay":
        return RazorpayProvider(config["RAZORPAY_KEY_ID"], config["RAZORPAY_KEY_SECRET"])
    return MockProvider()


def create_order(db, user, event, plan_id, amount_paise):
    provider = current_app.extensions["payment_provider"]
    try:
        order = provider.create_order(
            amount_paise,
            f"evt{event['id']}-{secrets.token_hex(4)}",
            {"event_id": str(event["id"]), "plan": plan_id, "email": user["email"]},
        )
    except (urllib.error.URLError, ValueError, OSError):
        return api_error("payment_gateway_error", "The payment gateway is unavailable. Please try again.", 502)
    db.execute(
        """INSERT INTO payments (user_id, event_id, plan_id, provider, provider_order_id,
                                 amount_paise, currency, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'INR', 'created', ?)""",
        (user["id"], event["id"], plan_id, provider.name, order["id"], amount_paise, util.iso(util.now())),
    )
    return jsonify(
        {
            "provider": provider.name,
            "order_id": order["id"],
            "amount_paise": amount_paise,
            "currency": "INR",
            "key_id": current_app.config["RAZORPAY_KEY_ID"] if provider.name == "razorpay" else "",
            "plan": public_plan(get_plan(plan_id)),
            "event": event_dict(db, event),
            "prefill": {"name": user["name"], "email": user["email"]},
        }
    )


def mark_paid(db, payment, provider_payment_id):
    """Idempotently settle a payment and activate or upgrade its event."""
    with tx(db):
        updated = db.execute(
            """UPDATE payments SET status = 'paid', provider_payment_id = ?, paid_at = ?
               WHERE id = ? AND status = 'created'""",
            (provider_payment_id, util.iso(util.now()), payment["id"]),
        ).rowcount
        if not updated:
            return False
        db.execute(
            "UPDATE events SET plan_id = ?, status = 'active', activated_at = COALESCE(activated_at, ?) WHERE id = ?",
            (payment["plan_id"], util.iso(util.now()), payment["event_id"]),
        )
        for invite in db.execute("SELECT id, created_at FROM invites WHERE event_id = ?", (payment["event_id"],)).fetchall():
            db.execute(
                "UPDATE invites SET expires_at = ? WHERE id = ?",
                (invite_expiry(invite["created_at"], payment["plan_id"]), invite["id"]),
            )
    return True


def _own_payment_by_order(db, user, order_id):
    return db.execute(
        "SELECT * FROM payments WHERE provider_order_id = ? AND user_id = ?", (order_id, user["id"])
    ).fetchone()


def _settled_response(db, payment):
    event = db.execute("SELECT * FROM events WHERE id = ?", (payment["event_id"],)).fetchone()
    return jsonify({"status": "paid", "event": event_dict(db, event)})


@bp.post("/api/payments/order")
@login_required
def order_for_pending_event():
    data = request.get_json(silent=True) or {}
    db = get_db()
    user = current_user()
    event = get_event_for_user(db, data.get("event_id"), user["id"]) if isinstance(data.get("event_id"), int) else None
    if event is None:
        return api_error("not_found", "Event not found.", 404)
    if event["status"] != "pending_payment":
        return api_error("already_paid", "This event is already active.", 409)
    return create_order(db, user, event, event["plan_id"], get_plan(event["plan_id"])["price_paise"])


@bp.post("/api/events/<int:event_id>/upgrade")
@login_required
def upgrade_event(event_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    user = current_user()
    event = get_event_for_user(db, event_id, user["id"])
    if event is None:
        return api_error("not_found", "Event not found.", 404)
    if event["status"] != "active":
        return api_error("event_not_active", "Complete the payment for this event first.", 409)
    target = data.get("plan")
    if not isinstance(target, str) or get_plan(target) is None:
        return api_error("invalid_plan", "Choose a valid plan.", 400)
    price = upgrade_price(event["plan_id"], target)
    if not price:
        return api_error("not_an_upgrade", "Choose a higher plan to upgrade.", 400)
    return create_order(db, user, event, target, price)


@bp.post("/api/payments/verify")
@login_required
def verify_payment():
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")
    if not all(isinstance(value, str) and value for value in (order_id, payment_id, signature)):
        return api_error("invalid_request", "Missing payment details.", 400)
    provider = current_app.extensions["payment_provider"]
    if provider.name != "razorpay":
        return api_error("not_found", "Not found.", 404)
    db = get_db()
    payment = _own_payment_by_order(db, current_user(), order_id)
    if payment is None:
        return api_error("not_found", "Payment not found.", 404)
    if not provider.verify_signature(order_id, payment_id, signature):
        return api_error("invalid_signature", "Payment verification failed.", 400)
    mark_paid(db, payment, payment_id)
    return _settled_response(db, payment)


@bp.post("/api/payments/mock-confirm")
@login_required
def mock_confirm():
    if current_app.extensions["payment_provider"].name != "mock":
        return api_error("not_found", "Not found.", 404)
    data = request.get_json(silent=True) or {}
    db = get_db()
    payment = _own_payment_by_order(db, current_user(), data.get("order_id"))
    if payment is None:
        return api_error("not_found", "Payment not found.", 404)
    mark_paid(db, payment, f"mock_pay_{secrets.token_hex(8)}")
    return _settled_response(db, payment)


@bp.post("/api/payments/razorpay/webhook")
def razorpay_webhook():
    secret = current_app.config["RAZORPAY_WEBHOOK_SECRET"]
    if not secret:
        return api_error("not_found", "Not found.", 404)
    body = request.get_data()
    if not verify_webhook_signature(secret, body, request.headers.get("X-Razorpay-Signature", "")):
        return api_error("invalid_signature", "Invalid webhook signature.", 400)
    try:
        payload = json.loads(body)
        if payload.get("event") in ("payment.captured", "order.paid"):
            entity = payload["payload"]["payment"]["entity"]
            db = get_db()
            payment = db.execute(
                "SELECT * FROM payments WHERE provider_order_id = ?", (entity["order_id"],)
            ).fetchone()
            if payment and entity.get("amount") == payment["amount_paise"]:
                mark_paid(db, payment, entity["id"])
    except (ValueError, KeyError, TypeError):
        return api_error("invalid_request", "Malformed webhook payload.", 400)
    return jsonify({"ok": True})


@bp.get("/api/payments")
@login_required
def list_payments():
    rows = get_db().execute(
        """SELECT p.id, p.event_id, e.title AS event_title, p.plan_id, p.provider, p.provider_order_id,
                  p.provider_payment_id, p.amount_paise, p.currency, p.status, p.created_at, p.paid_at
           FROM payments p JOIN events e ON e.id = p.event_id
           WHERE p.user_id = ? ORDER BY p.id DESC""",
        (current_user()["id"],),
    ).fetchall()
    return jsonify({"payments": [dict(row) for row in rows]})
