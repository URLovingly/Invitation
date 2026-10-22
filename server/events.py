import json
import os
import re
import secrets
from urllib.parse import quote

from flask import Blueprint, current_app, jsonify, request

from . import util
from .auth import current_user, login_required, user_dict
from .db import get_db, tx
from .errors import api_error
from .imports import parse_guest_file
from .models import (
    active_features,
    available_templates,
    base_url,
    event_dict,
    get_event_for_user,
    invite_expiry,
)
from .plans import FEATURE_LABELS, PLANS, cheapest_plan_with, get_plan, public_plan

bp = Blueprint("events", __name__)

UPI_PATTERN = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")
DEFAULT_WHATSAPP_TEMPLATE = (
    "Hi {guest_name}! You are warmly invited to {couple_names}'s {event_type}. "
    "Your personal invitation is here: {link}"
)
WHATSAPP_TOKENS = re.compile(r"\{(guest_name|couple_names|event_type|link)\}")


def _json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _text(value, max_length, required=False):
    """Return a trimmed string, or None when the value is invalid."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value and required:
        return None
    return value if len(value) <= max_length else None


def _load_event(event_id, feature=None):
    """Return (event, error_response); optionally require an active event that includes `feature`."""
    db = get_db()
    event = get_event_for_user(db, event_id, current_user()["id"])
    if event is None:
        return None, api_error("not_found", "Event not found.", 404)
    if feature is not None:
        if event["status"] != "active":
            return None, api_error("event_not_active", "Complete the payment for this event first.", 402)
        if feature not in active_features(event):
            return None, api_error(
                "feature_not_in_plan",
                f"{FEATURE_LABELS[feature]} is not included in your plan.",
                403,
                feature=feature,
                required_plan=cheapest_plan_with(feature),
            )
    return event, None


def invite_dict(invite):
    return {
        "id": invite["id"],
        "guest_name": invite["guest_name"],
        "guest_phone": invite["guest_phone"],
        "couple_names": invite["couple_names"],
        "event_type": invite["event_type"],
        "template": invite["template"],
        "url": f"{base_url()}/{invite['couple_slug']}/to/{invite['guest_slug']}/",
        "allowed_ceremonies": json.loads(invite["allowed_ceremonies"]),
        "created_at": invite["created_at"],
        "expires_at": invite["expires_at"],
        "expired": util.parse_iso(invite["expires_at"]) <= util.now(),
    }


@bp.get("/api/plans")
def list_plans():
    plans = sorted(PLANS.values(), key=lambda plan: plan["sort_order"])
    return jsonify({"plans": [public_plan(plan) for plan in plans], "feature_labels": FEATURE_LABELS})


@bp.get("/api/config")
def public_config():
    config = current_app.config
    return jsonify(
        {
            "google_client_id": config["GOOGLE_CLIENT_ID"],
            "dev_login": config["ALLOW_DEV_LOGIN"],
            "payment_provider": config["PAYMENT_PROVIDER"],
            "razorpay_key_id": config["RAZORPAY_KEY_ID"] if config["PAYMENT_PROVIDER"] == "razorpay" else "",
        }
    )


@bp.get("/api/me")
@login_required
def me():
    db = get_db()
    user = current_user()
    events = db.execute("SELECT * FROM events WHERE user_id = ? ORDER BY id", (user["id"],)).fetchall()
    return jsonify(
        {
            "user": user_dict(user),
            "events": [event_dict(db, event) for event in events],
            "trial_used": any(event["is_trial"] for event in events),
        }
    )


@bp.post("/api/events")
@login_required
def create_event():
    data = _json()
    plan = get_plan(data.get("plan")) if isinstance(data.get("plan"), str) else None
    if plan is None:
        return api_error("invalid_plan", "Choose a valid plan.", 400)
    title = _text(data.get("title", "My Celebration"), 120, required=True)
    if title is None:
        return api_error("invalid_title", "Give your event a name (up to 120 characters).", 400)

    db = get_db()
    user = current_user()
    moment = util.iso(util.now())
    is_free = plan["price_paise"] == 0
    with tx(db):
        if is_free:
            if db.execute("SELECT 1 FROM events WHERE user_id = ? AND is_trial = 1", (user["id"],)).fetchone():
                return api_error("trial_already_used", "The free trial can be used once per account.", 409)
        else:
            pending = db.execute(
                "SELECT * FROM events WHERE user_id = ? AND plan_id = ? AND status = 'pending_payment' LIMIT 1",
                (user["id"], plan["id"]),
            ).fetchone()
            if pending:
                return jsonify({"event": event_dict(db, pending)}), 200
        cursor = db.execute(
            """INSERT INTO events (public_id, user_id, plan_id, title, status, is_trial, created_at, activated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                secrets.token_urlsafe(9),
                user["id"],
                plan["id"],
                title,
                "active" if is_free else "pending_payment",
                int(is_free),
                moment,
                moment if is_free else None,
            ),
        )
        event = db.execute("SELECT * FROM events WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify({"event": event_dict(db, event)}), 201


@bp.get("/api/events/<int:event_id>")
@login_required
def get_event(event_id):
    event, error = _load_event(event_id)
    return error or jsonify({"event": event_dict(get_db(), event)})


@bp.get("/api/events/<int:event_id>/invites")
@login_required
def list_invites(event_id):
    event, error = _load_event(event_id)
    if error:
        return error
    rows = get_db().execute("SELECT * FROM invites WHERE event_id = ? ORDER BY id DESC", (event_id,)).fetchall()
    return jsonify({"invites": [invite_dict(row) for row in rows]})


@bp.post("/api/events/<int:event_id>/guest-import/preview")
@login_required
def preview_guest_import(event_id):
    event, error = _load_event(event_id)
    if error:
        return error
    if event["status"] != "active":
        return api_error("event_not_active", "Complete the payment for this event first.", 402)
    upload = request.files.get("file")
    if upload is None:
        return api_error("invalid_file", "Choose a CSV or .xlsx guest spreadsheet.", 400)
    try:
        guests = parse_guest_file(upload.filename, upload.stream.read())
    except ValueError as error:
        return api_error("invalid_file", str(error), 400)
    return jsonify({"guests": guests, "event": event_dict(get_db(), event)})


@bp.post("/api/events/<int:event_id>/invites")
@login_required
def create_invite(event_id):
    event, error = _load_event(event_id, feature=None)
    if error:
        return error
    if event["status"] != "active":
        return api_error("event_not_active", "Complete the payment for this event first.", 402)

    data = _json()
    config = current_app.config
    guest_name = _text(data.get("name"), 100, required=True)
    couple_names = _text(data.get("couple_names"), 150, required=True)
    event_type = _text(data.get("event_type", "Wedding"), 100, required=True)
    html = data.get("rendered_html")
    if guest_name is None or couple_names is None or event_type is None:
        return api_error("invalid_request", "Guest name, celebration names and event type are required.", 400)
    if data.get("template") not in available_templates():
        return api_error("invalid_template", "Choose one of the available invitation designs.", 400)
    if not isinstance(html, str) or not html.strip() or len(html.encode("utf-8")) > config["MAX_INVITE_HTML_BYTES"]:
        return api_error("invalid_html", "The invitation content is missing or too large.", 400)

    ceremonies = data.get("allowed_ceremonies") or []
    if not isinstance(ceremonies, list) or len(ceremonies) > 30 or not all(
        isinstance(item, str) and 0 < len(item) <= 120 for item in ceremonies
    ):
        return api_error("invalid_request", "allowed_ceremonies must be a list of ceremony names.", 400)
    features = active_features(event)
    if ceremonies and "multi_day_routing" not in features:
        return api_error(
            "feature_not_in_plan",
            f"{FEATURE_LABELS['multi_day_routing']} is not included in your plan.",
            403,
            feature="multi_day_routing",
            required_plan=cheapest_plan_with("multi_day_routing"),
        )

    phone = ""
    if "whatsapp_generator" in features:
        phone = normalise_phone(data.get("guest_phone"))

    user = current_user()
    plan = get_plan(event["plan_id"])
    couple_slug = util.slugify(couple_names, "event")
    guest_slug = util.slugify(guest_name, "guest")
    moment = util.iso(util.now())
    db = get_db()
    with tx(db):
        existing = db.execute(
            "SELECT * FROM invites WHERE couple_slug = ? AND guest_slug = ?", (couple_slug, guest_slug)
        ).fetchone()
        if existing and existing["event_id"] != event["id"]:
            return api_error("slug_taken", "This invitation link is already in use. Change the names slightly.", 409)
        values = (guest_name, phone, couple_names, event_type, data["template"], json.dumps(ceremonies), html, moment)
        if existing:
            db.execute(
                """UPDATE invites SET guest_name=?, guest_phone=?, couple_names=?, event_type=?, template=?,
                          allowed_ceremonies=?, html=?, updated_at=? WHERE id=?""",
                (*values, existing["id"]),
            )
            invite_id, created = existing["id"], False
        else:
            used = db.execute("SELECT COUNT(*) FROM invites WHERE event_id = ?", (event["id"],)).fetchone()[0]
            if used >= plan["link_limit"]:
                return api_error(
                    "link_limit_reached",
                    f"Your plan allows up to {plan['link_limit']} personalized guest links.",
                    403,
                    limit=plan["link_limit"],
                )
            cursor = db.execute(
                """INSERT INTO invites (public_id, event_id, user_id, host_email, guest_name, guest_phone,
                                        couple_names, event_type, couple_slug, guest_slug, template,
                                        allowed_ceremonies, html, created_at, updated_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    secrets.token_urlsafe(9), event["id"], user["id"], user["email"], guest_name, phone,
                    couple_names, event_type, couple_slug, guest_slug, data["template"], json.dumps(ceremonies),
                    html, moment, moment, invite_expiry(moment, plan["id"]),
                ),
            )
            invite_id, created = cursor.lastrowid, True
    invite = db.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()
    return jsonify({"invite": invite_dict(invite), "event": event_dict(db, event)}), 201 if created else 200


def normalise_phone(value):
    digits = re.sub(r"\D", "", value) if isinstance(value, str) else ""
    if len(digits) == 10:
        digits = "91" + digits
    return digits if 11 <= len(digits) <= 15 else ""


@bp.post("/api/events/<int:event_id>/whatsapp")
@login_required
def whatsapp_messages(event_id):
    event, error = _load_event(event_id, "whatsapp_generator")
    if error:
        return error
    template = _json().get("template") or DEFAULT_WHATSAPP_TEMPLATE
    template = _text(template, 1000, required=True)
    if template is None:
        return api_error("invalid_template", "Write a message of up to 1000 characters.", 400)
    rows = get_db().execute("SELECT * FROM invites WHERE event_id = ? ORDER BY id", (event_id,)).fetchall()
    messages = []
    for row in rows:
        invite = invite_dict(row)
        values = {
            "guest_name": invite["guest_name"],
            "couple_names": invite["couple_names"],
            "event_type": invite["event_type"].lower(),
            "link": invite["url"],
        }
        text = WHATSAPP_TOKENS.sub(lambda match: values[match.group(1)], template)
        target = invite["guest_phone"]
        messages.append(
            {
                "invite_id": invite["id"],
                "guest_name": invite["guest_name"],
                "phone": target,
                "message": text,
                "url": f"https://wa.me/{target}?text={quote(text)}",
            }
        )
    return jsonify({"template": template, "messages": messages})


@bp.get("/api/events/<int:event_id>/rsvps")
@login_required
def rsvp_dashboard(event_id):
    event, error = _load_event(event_id, "rsvp_dashboard")
    if error:
        return error
    rows = get_db().execute(
        """SELECT i.id AS invite_id, i.guest_name, r.response, r.guests, r.message, r.updated_at
           FROM invites i LEFT JOIN rsvps r ON r.invite_id = i.id
           WHERE i.event_id = ? ORDER BY i.id""",
        (event_id,),
    ).fetchall()
    items = [dict(row) for row in rows]
    summary = {"yes": 0, "no": 0, "maybe": 0, "pending": 0, "attending_guests": 0}
    for item in items:
        summary[item["response"] or "pending"] += 1
        if item["response"] == "yes":
            summary["attending_guests"] += item["guests"]
    return jsonify({"summary": summary, "items": items})


@bp.put("/api/events/<int:event_id>/settings")
@login_required
def update_settings(event_id):
    event, error = _load_event(event_id, "upi_shagun")
    if error:
        return error
    data = _json()
    upi_id = _text(data.get("upi_id", ""), 256)
    upi_name = _text(data.get("upi_name", ""), 80)
    if upi_id is None or upi_name is None or (upi_id and not UPI_PATTERN.match(upi_id)):
        return api_error("invalid_upi", "Enter a valid UPI ID such as name@bank.", 400)
    db = get_db()
    db.execute("UPDATE events SET upi_id = ?, upi_name = ? WHERE id = ?", (upi_id, upi_name, event_id))
    return jsonify({"event": event_dict(db, db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())})


def sniff_audio(content):
    if content[:3] == b"ID3" or (len(content) > 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0):
        return "mp3", "audio/mpeg"
    if content[4:8] == b"ftyp":
        return "m4a", "audio/mp4"
    if content[:4] == b"OggS":
        return "ogg", "audio/ogg"
    return None


def audio_path(event):
    return os.path.join(current_app.config["MEDIA_DIR"], "audio", event["audio_file"])


def _remove_audio_file(event):
    if event["audio_file"]:
        try:
            os.remove(audio_path(event))
        except FileNotFoundError:
            pass


@bp.post("/api/events/<int:event_id>/audio")
@login_required
def upload_audio(event_id):
    event, error = _load_event(event_id, "custom_audio")
    if error:
        return error
    upload = request.files.get("audio")
    if upload is None:
        return api_error("invalid_request", "Attach an audio file in the 'audio' field.", 400)
    content = upload.read(current_app.config["MAX_AUDIO_BYTES"] + 1)
    if len(content) > current_app.config["MAX_AUDIO_BYTES"]:
        return api_error("audio_too_large", "Audio must be 3 MB or smaller.", 413)
    kind = sniff_audio(content)
    if kind is None:
        return api_error("invalid_audio", "Upload an MP3, M4A or OGG audio file.", 400)
    extension, mimetype = kind

    _remove_audio_file(event)
    filename = f"{event['public_id']}.{extension}"
    os.makedirs(os.path.join(current_app.config["MEDIA_DIR"], "audio"), exist_ok=True)
    with open(os.path.join(current_app.config["MEDIA_DIR"], "audio", filename), "wb") as target:
        target.write(content)
    db = get_db()
    db.execute("UPDATE events SET audio_file = ?, audio_type = ? WHERE id = ?", (filename, mimetype, event_id))
    return jsonify({"event": event_dict(db, db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())})


@bp.delete("/api/events/<int:event_id>/audio")
@login_required
def delete_audio(event_id):
    event, error = _load_event(event_id, "custom_audio")
    if error:
        return error
    _remove_audio_file(event)
    db = get_db()
    db.execute("UPDATE events SET audio_file = '', audio_type = '' WHERE id = ?", (event_id,))
    return jsonify({"event": event_dict(db, db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())})
