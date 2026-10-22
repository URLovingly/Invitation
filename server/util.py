import re
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc)


def iso(moment):
    return moment.isoformat()


def parse_iso(value):
    return datetime.fromisoformat(value)


def slugify(text, fallback):
    text = (text or "").lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or fallback
