import json
import os
from html import escape
from urllib.parse import quote

from flask import Blueprint, current_app, redirect, request, send_file, send_from_directory

from . import util
from .auth import current_user
from .config import BASE_DIR
from .db import get_db
from .errors import api_error
from .models import active_features, available_templates, base_url
from .plans import plan_has

bp = Blueprint("pages", __name__)

INVITE_CSP = "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation"
RSVP_RESPONSES = ("yes", "no", "maybe")


def _no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/")
def landing():
    return send_file(os.path.join(BASE_DIR, "index.html"), max_age=0)


@bp.get("/URLovingly_Icon.jpg")
def logo():
    return send_file(os.path.join(BASE_DIR, "URLovingly_Icon.jpg"))


@bp.get("/studio")
def studio():
    user = current_user()
    if user is None:
        return redirect("/?signin=1")
    active = get_db().execute(
        "SELECT 1 FROM events WHERE user_id = ? AND status = 'active' LIMIT 1", (user["id"],)
    ).fetchone()
    if not active:
        return redirect("/?choose=plan")
    return _no_store(send_file(os.path.join(BASE_DIR, "private", "studio.html")))


@bp.get("/templates/<name>/index.html")
def invitation_template(name):
    if current_user() is None:
        return api_error("unauthenticated", "Please sign in to continue.", 401)
    if name not in available_templates():
        return api_error("not_found", "Template not found.", 404)
    return send_from_directory(os.path.join(BASE_DIR, "templates", name), "index.html", max_age=0)


def _json_for_script(value):
    return json.dumps(value).replace("<", "\\u003c")


def _rsvp_block(endpoint):
    return f"""
<section id="ul-rsvp" style="max-width:420px;margin:24px auto;padding:20px;border:1px solid rgba(0,0,0,.15);border-radius:14px;background:#fff;color:#222;font:14px system-ui,sans-serif;text-align:center">
  <h2 style="margin:0 0 12px;font:600 20px Georgia,serif">Will you join us?</h2>
  <div style="display:flex;gap:8px;justify-content:center;margin-bottom:12px">
    <button type="button" data-ul-response="yes" style="padding:8px 14px;border-radius:999px;border:1px solid #222;background:#fff;cursor:pointer">Yes</button>
    <button type="button" data-ul-response="maybe" style="padding:8px 14px;border-radius:999px;border:1px solid #222;background:#fff;cursor:pointer">Maybe</button>
    <button type="button" data-ul-response="no" style="padding:8px 14px;border-radius:999px;border:1px solid #222;background:#fff;cursor:pointer">No</button>
  </div>
  <label style="display:block;margin-bottom:8px">Guests attending <input id="ul-rsvp-guests" type="number" min="1" max="20" value="1" style="width:64px;padding:4px"></label>
  <textarea id="ul-rsvp-message" maxlength="300" rows="2" placeholder="A message for the hosts (optional)" style="width:100%;box-sizing:border-box;padding:8px;border:1px solid #ccc;border-radius:8px"></textarea>
  <p id="ul-rsvp-status" role="status" style="min-height:1.2em;margin:8px 0 0"></p>
</section>
<script>
(function () {{
  var endpoint = {_json_for_script(endpoint)};
  var status = document.getElementById('ul-rsvp-status');
  document.querySelectorAll('[data-ul-response]').forEach(function (button) {{
    button.addEventListener('click', function () {{
      var response = button.getAttribute('data-ul-response');
      var guests = parseInt(document.getElementById('ul-rsvp-guests').value, 10) || 1;
      status.textContent = 'Sending...';
      fetch(endpoint, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ response: response, guests: guests, message: document.getElementById('ul-rsvp-message').value }})
      }}).then(function (r) {{ return r.json().then(function (body) {{ return {{ ok: r.ok, body: body }}; }}); }})
        .then(function (result) {{ status.textContent = result.ok ? 'Thank you! Your reply has been sent.' : (result.body.message || 'Could not send your reply.'); }})
        .catch(function () {{ status.textContent = 'Could not send your reply. Please try again.'; }});
    }});
  }});
}})();
</script>"""


def _upi_block(event):
    payee = event["upi_name"] or event["title"]
    link = f"upi://pay?pa={quote(event['upi_id'], safe='@')}&pn={quote(payee)}&cu=INR"
    return f"""
<section id="ul-upi" style="max-width:420px;margin:24px auto;padding:20px;border:1px solid rgba(0,0,0,.15);border-radius:14px;background:#fff;color:#222;font:14px system-ui,sans-serif;text-align:center">
  <h2 style="margin:0 0 8px;font:600 20px Georgia,serif">Send your blessings</h2>
  <p style="margin:0 0 12px">Shagun to {escape(payee)}<br><strong>{escape(event['upi_id'])}</strong></p>
  <a href="{escape(link, quote=True)}" style="display:inline-block;padding:10px 18px;border-radius:999px;background:#222;color:#fff;text-decoration:none">Pay Shagun with UPI</a>
</section>"""


def _audio_block(event):
    source = f"{base_url()}/media/audio/{event['public_id']}"
    return f"""
<audio id="ul-audio" src="{escape(source, quote=True)}" loop preload="none"></audio>
<button id="ul-audio-toggle" type="button" aria-label="Toggle background music" style="position:fixed;right:14px;bottom:14px;z-index:10000;width:44px;height:44px;border-radius:50%;border:0;background:#222;color:#fff;font-size:18px;cursor:pointer">&#9835;</button>
<script>
(function () {{
  var audio = document.getElementById('ul-audio');
  var toggle = document.getElementById('ul-audio-toggle');
  var started = false;
  function play() {{ audio.play().then(function () {{ toggle.style.opacity = '1'; }}).catch(function () {{}}); }}
  function startOnce() {{ if (!started) {{ started = true; play(); }} }}
  document.addEventListener('pointerdown', startOnce, {{ once: true }});
  document.addEventListener('keydown', startOnce, {{ once: true }});
  toggle.addEventListener('click', function (event) {{
    event.stopPropagation();
    started = true;
    if (audio.paused) {{ play(); }} else {{ audio.pause(); toggle.style.opacity = '.55'; }}
  }});
}})();
</script>"""


def render_invite(invite, event):
    features = active_features(event)
    blocks = []
    if "rsvp_dashboard" in features:
        blocks.append(_rsvp_block(f"{base_url()}/api/rsvp/{invite['public_id']}"))
    if "upi_shagun" in features and event["upi_id"]:
        blocks.append(_upi_block(event))
    if "custom_audio" in features and event["audio_file"]:
        blocks.append(_audio_block(event))
    if not blocks:
        return invite["html"]
    injected = "".join(blocks)
    html = invite["html"]
    position = html.lower().rfind("</body>")
    return html + injected if position == -1 else html[:position] + injected + html[position:]


def _status_page(title, message, status):
    body = (
        f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width,initial-scale=1'><title>{escape(title)}</title></head>"
        f"<body style='font-family:system-ui,sans-serif;text-align:center;padding:4rem 1rem'>"
        f"<h1>{escape(title)}</h1><p>{escape(message)}</p></body></html>"
    )
    response = current_app.response_class(body, status=status, mimetype="text/html")
    response.headers["Content-Security-Policy"] = INVITE_CSP
    return response


@bp.get("/<couple_slug>/to/<guest_slug>/")
def serve_invite(couple_slug, guest_slug):
    db = get_db()
    invite = db.execute(
        "SELECT * FROM invites WHERE couple_slug = ? AND guest_slug = ?", (couple_slug, guest_slug)
    ).fetchone()
    if invite is None:
        return _status_page("Invitation not found", "This invitation link does not exist.", 404)
    if util.parse_iso(invite["expires_at"]) <= util.now():
        return _status_page("Invitation expired", "The hosting period for this invitation has ended.", 410)
    event = db.execute("SELECT * FROM events WHERE id = ?", (invite["event_id"],)).fetchone()
    response = current_app.response_class(render_invite(invite, event), mimetype="text/html")
    # Invitation markup is customer-supplied; the sandbox gives it an opaque origin so it cannot reach our cookies or APIs.
    response.headers["Content-Security-Policy"] = INVITE_CSP
    response.headers["Referrer-Policy"] = "no-referrer"
    return _no_store(response)


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@bp.route("/api/rsvp/<public_id>", methods=["POST", "OPTIONS"])
def submit_rsvp(public_id):
    if request.method == "OPTIONS":
        return _cors(current_app.response_class(status=204))
    db = get_db()
    row = db.execute(
        """SELECT i.id, i.expires_at, e.plan_id, e.status FROM invites i
           JOIN events e ON e.id = i.event_id WHERE i.public_id = ?""",
        (public_id,),
    ).fetchone()
    if row is None or row["status"] != "active" or util.parse_iso(row["expires_at"]) <= util.now():
        return _cors(api_error("not_found", "This invitation is no longer accepting replies.", 404))
    if not plan_has(row["plan_id"], "rsvp_dashboard"):
        return _cors(api_error("feature_not_in_plan", "RSVP is not enabled for this invitation.", 403))

    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    response_value = data.get("response")
    guests = data.get("guests", 1)
    message = data.get("message", "")
    if (
        response_value not in RSVP_RESPONSES
        or isinstance(guests, bool)
        or not isinstance(guests, int)
        or not 1 <= guests <= 20
        or not isinstance(message, str)
        or len(message) > 300
    ):
        return _cors(api_error("invalid_request", "Please choose Yes, Maybe or No and a guest count from 1 to 20.", 400))
    db.execute(
        """INSERT INTO rsvps (invite_id, response, guests, message, updated_at) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(invite_id) DO UPDATE SET response = excluded.response, guests = excluded.guests,
             message = excluded.message, updated_at = excluded.updated_at""",
        (row["id"], response_value, guests, message.strip(), util.iso(util.now())),
    )
    return _cors(current_app.response_class(json.dumps({"ok": True}), mimetype="application/json"))


@bp.get("/media/audio/<public_id>")
def serve_audio(public_id):
    event = get_db().execute("SELECT * FROM events WHERE public_id = ?", (public_id,)).fetchone()
    if event is None or not event["audio_file"] or "custom_audio" not in active_features(event):
        return api_error("not_found", "Audio not found.", 404)
    directory = os.path.join(current_app.config["MEDIA_DIR"], "audio")
    response = send_from_directory(directory, event["audio_file"], mimetype=event["audio_type"], conditional=True)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
