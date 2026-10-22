import os
from datetime import timedelta

from flask import current_app, request

from . import util
from .config import BASE_DIR
from .plans import PLANS, get_plan, public_plan

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


def available_templates():
    return sorted(
        name for name in os.listdir(TEMPLATES_DIR) if os.path.isfile(os.path.join(TEMPLATES_DIR, name, "index.html"))
    )


def base_url():
    return current_app.config["PUBLIC_BASE_URL"] or request.host_url.rstrip("/")


def get_event_for_user(db, event_id, user_id):
    return db.execute("SELECT * FROM events WHERE id = ? AND user_id = ?", (event_id, user_id)).fetchone()


def links_used(db, event_id):
    return db.execute("SELECT COUNT(*) FROM invites WHERE event_id = ?", (event_id,)).fetchone()[0]


def active_features(event):
    if event["status"] != "active":
        return []
    return list(get_plan(event["plan_id"])["features"])


def event_dict(db, event):
    plan = get_plan(event["plan_id"])
    used = links_used(db, event["id"])
    return {
        "id": event["id"],
        "public_id": event["public_id"],
        "title": event["title"],
        "status": event["status"],
        "plan": public_plan(plan),
        "features": active_features(event),
        "link_limit": plan["link_limit"],
        "links_used": used,
        "links_remaining": max(plan["link_limit"] - used, 0),
        "hosting_days": plan["hosting_days"],
        "upi_id": event["upi_id"],
        "upi_name": event["upi_name"],
        "audio_url": f"/media/audio/{event['public_id']}" if event["audio_file"] else "",
        "created_at": event["created_at"],
    }


def upgrade_price(current_plan_id, target_plan_id):
    """Price in paise to move an event up to target_plan_id, or None if it is not an upgrade."""
    current, target = PLANS[current_plan_id], PLANS[target_plan_id]
    if target["sort_order"] <= current["sort_order"]:
        return None
    return target["price_paise"] - current["price_paise"]


def invite_expiry(created_at_iso, plan_id):
    return util.iso(util.parse_iso(created_at_iso) + timedelta(days=get_plan(plan_id)["hosting_days"]))
