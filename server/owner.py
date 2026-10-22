"""Read-only owner dashboard, restricted to a configured Google account."""
import os

from flask import Blueprint, current_app, jsonify, redirect, send_file

from .auth import current_user
from .config import BASE_DIR
from .db import get_db

bp = Blueprint("owner", __name__)


def _owner_access():
    user = current_user()
    if user is None:
        return None, (jsonify({"error": "unauthenticated", "message": "Sign in to continue."}), 401)
    owner_email = (current_app.config.get("OWNER_EMAIL") or "").strip().lower()
    if not owner_email or user["email"].strip().lower() != owner_email or not user["google_sub"]:
        return None, (jsonify({"error": "not_found", "message": "Not found."}), 404)
    return user, None


def _private(response):
    response.headers["Cache-Control"] = "private, no-store, no-cache, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    return response


@bp.get("/owner")
def owner_dashboard():
    user = current_user()
    if user is None:
        return redirect("/?signin=1")
    authorized, error = _owner_access()
    if error:
        return "Not found", 404
    response = send_file(os.path.join(BASE_DIR, "private", "owner.html"), max_age=0)
    return _private(response)


@bp.get("/api/owner/overview")
def owner_overview():
    _, error = _owner_access()
    if error:
        response, status = error
        response.status_code = status
        return _private(response)

    db = get_db()
    user_rows = db.execute(
        "SELECT id, email, name, created_at, last_login_at FROM users ORDER BY created_at DESC, id DESC"
    ).fetchall()
    event_rows = db.execute(
        """SELECT e.id, e.public_id, e.user_id, e.title, e.status, e.plan_id, p.name AS plan_name,
                  e.is_trial, e.created_at, e.audio_file, e.audio_type
           FROM events e JOIN plans p ON p.id = e.plan_id
           ORDER BY e.created_at DESC, e.id DESC"""
    ).fetchall()
    invite_rows = db.execute(
        """SELECT id, event_id, guest_name, couple_slug, guest_slug, template, created_at, expires_at,
                  length(CAST(html AS BLOB)) AS html_bytes,
                  (length(html) - length(replace(html, 'data:image/', ''))) / length('data:image/') AS photo_count
           FROM invites ORDER BY created_at DESC, id DESC"""
    ).fetchall()

    customers = {
        row["id"]: {
            "email": row["email"],
            "name": row["name"],
            "created_at": row["created_at"],
            "last_login_at": row["last_login_at"],
            "events": [],
        }
        for row in user_rows
    }
    events = {}
    for row in event_rows:
        event = {
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "plan_id": row["plan_id"],
            "plan_name": row["plan_name"],
            "is_trial": bool(row["is_trial"]),
            "created_at": row["created_at"],
            "links": [],
            "assets": [],
            "stored_html_bytes": 0,
            "embedded_photo_count": 0,
        }
        if row["audio_file"]:
            filename = row["audio_file"]
            safe_filename = os.path.basename(filename) == filename
            audio_path = os.path.join(current_app.config["MEDIA_DIR"], "audio", filename) if safe_filename else ""
            try:
                size_bytes = os.path.getsize(audio_path) if audio_path else None
            except OSError:
                size_bytes = None
            event["assets"].append({
                "kind": "background audio",
                "name": filename,
                "content_type": row["audio_type"],
                "size_bytes": size_bytes,
                "available": size_bytes is not None,
                "url": f"/media/audio/{row['public_id']}",
            })
        customers[row["user_id"]]["events"].append(event)
        events[row["id"]] = event

    for row in invite_rows:
        event = events.get(row["event_id"])
        if event is None:
            continue
        html_bytes = row["html_bytes"] or 0
        photo_count = row["photo_count"] or 0
        event["stored_html_bytes"] += html_bytes
        event["embedded_photo_count"] += photo_count
        event["links"].append({
            "guest_name": row["guest_name"],
            "url": f"/{row['couple_slug']}/to/{row['guest_slug']}/",
            "template": row["template"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "stored_html_bytes": html_bytes,
            "embedded_photo_count": photo_count,
        })

    for customer in customers.values():
        customer["events"].sort(key=lambda event: event["created_at"], reverse=True)

    summary = {
        "customer_count": len(customers),
        "event_count": len(event_rows),
        "link_count": len(invite_rows),
        "stored_bytes": sum(
            event["stored_html_bytes"] + sum(asset["size_bytes"] or 0 for asset in event["assets"])
            for customer in customers.values() for event in customer["events"]
        ),
    }
    return _private(jsonify({"summary": summary, "customers": list(customers.values())}))
