import hashlib
import re
import secrets
from datetime import timedelta
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

from . import util
from .db import get_db
from .errors import api_error

bp = Blueprint("auth", __name__)

COOKIE_NAME = "urlovingly_session"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def default_google_verifier(client_id):
    def verify(credential):
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        return id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)

    return verify


def email_allowed(email):
    allowed = current_app.config["ALLOWED_EMAIL_DOMAINS"]
    return not allowed or email.rsplit("@", 1)[1] in allowed


def current_user():
    if "user" in g:
        return g.user
    g.user = None
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db = get_db()
        row = db.execute(
            """SELECT u.*, s.expires_at AS session_expires_at FROM sessions s
               JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?""",
            (hash_token(token),),
        ).fetchone()
        if row:
            if util.parse_iso(row["session_expires_at"]) > util.now():
                g.user = row
            else:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
    return g.user


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return api_error("unauthenticated", "Please sign in with Google to continue.", 401)
        return view(*args, **kwargs)

    return wrapper


def user_dict(user):
    return {"id": user["id"], "email": user["email"], "name": user["name"], "picture": user["picture"]}


def _finish_login(email, name, picture, google_sub):
    email = (email or "").strip().lower()
    if not EMAIL_PATTERN.match(email):
        return api_error("invalid_email", "A valid email address is required.", 400)
    if not email_allowed(email):
        return api_error("gmail_required", "Please sign in with your Gmail account.", 403)

    db = get_db()
    moment = util.iso(util.now())
    db.execute(
        """INSERT INTO users (email, name, picture, google_sub, created_at, last_login_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(email) DO UPDATE SET
             name = excluded.name, picture = excluded.picture,
             google_sub = COALESCE(excluded.google_sub, users.google_sub),
             last_login_at = excluded.last_login_at""",
        (email, (name or "")[:200], (picture or "")[:500], google_sub, moment, moment),
    )
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    token = secrets.token_urlsafe(32)
    ttl = timedelta(days=current_app.config["SESSION_TTL_DAYS"])
    db.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (hash_token(token), user["id"], moment, util.iso(util.now() + ttl)),
    )
    response = jsonify({"user": user_dict(user)})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="Lax",
        secure=current_app.config["SESSION_COOKIE_SECURE"],
        path="/",
    )
    return response


@bp.post("/api/auth/google")
def google_login():
    data = request.get_json(silent=True) or {}
    credential = data.get("credential")
    if not isinstance(credential, str) or not credential:
        return api_error("invalid_request", "Missing Google credential.", 400)
    try:
        info = current_app.extensions["google_verifier"](credential)
    except Exception:
        return api_error("invalid_credential", "Google sign-in could not be verified.", 401)
    if not info.get("email_verified"):
        return api_error("email_not_verified", "Your Google email is not verified.", 403)
    return _finish_login(info.get("email"), info.get("name"), info.get("picture"), info.get("sub"))


@bp.post("/api/auth/dev-login")
def dev_login():
    if not current_app.config["ALLOW_DEV_LOGIN"]:
        return api_error("not_found", "Not found.", 404)
    data = request.get_json(silent=True) or {}
    email = data.get("email") if isinstance(data.get("email"), str) else ""
    name = data.get("name") if isinstance(data.get("name"), str) else email.split("@")[0]
    return _finish_login(email, name, "", None)


@bp.post("/api/auth/logout")
def logout():
    token = request.cookies.get(COOKIE_NAME)
    if token:
        get_db().execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
    response = jsonify({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
