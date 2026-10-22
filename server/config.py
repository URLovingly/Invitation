import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Public OAuth client id (not a secret); override with GOOGLE_CLIENT_ID for your own deployment.
DEFAULT_GOOGLE_CLIENT_ID = "412855134600-qku667pr3h0713748chh1o5i7u0nfo9p.apps.googleusercontent.com"


def _split(value):
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def load_config(overrides=None):
    env = os.environ.get
    app_env = env("URLOVINGLY_ENV", "production")
    development = app_env == "development"
    key_id, key_secret = env("RAZORPAY_KEY_ID", ""), env("RAZORPAY_KEY_SECRET", "")
    config = {
        "ENV": app_env,
        "DATABASE": env("URLOVINGLY_DB", os.path.join(BASE_DIR, "data", "urlovingly.db")),
        "MEDIA_DIR": env("URLOVINGLY_MEDIA", os.path.join(BASE_DIR, "data", "media")),
        "GOOGLE_CLIENT_ID": env("GOOGLE_CLIENT_ID", DEFAULT_GOOGLE_CLIENT_ID),
        # Empty list disables the domain restriction.
        "ALLOWED_EMAIL_DOMAINS": _split(env("URLOVINGLY_ALLOWED_EMAIL_DOMAINS", "gmail.com,googlemail.com")),
        "ALLOW_DEV_LOGIN": env("URLOVINGLY_DEV_LOGIN", "1" if development else "0") == "1",
        "RAZORPAY_KEY_ID": key_id,
        "RAZORPAY_KEY_SECRET": key_secret,
        "RAZORPAY_WEBHOOK_SECRET": env("RAZORPAY_WEBHOOK_SECRET", ""),
        "PAYMENT_PROVIDER": "razorpay" if key_id and key_secret else "mock",
        "SESSION_TTL_DAYS": 7,
        "SESSION_COOKIE_SECURE": not development,
        "PUBLIC_BASE_URL": env("URLOVINGLY_PUBLIC_URL", "https://invite-guests.urlovingly-comp.workers.dev").rstrip("/"),
        "OWNER_EMAIL": env("URLOVINGLY_OWNER_EMAIL", "urlovingly.comp@gmail.com").strip().lower(),
        "MAX_CONTENT_LENGTH": 4 * 1024 * 1024,
        "MAX_AUDIO_BYTES": 3 * 1024 * 1024,
        "MAX_INVITE_HTML_BYTES": 400 * 1024,
    }
    if overrides:
        config.update(overrides)
    return config
