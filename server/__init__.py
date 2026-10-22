from flask import Flask, request

from . import auth, events, owner, pages, payments
from .config import load_config
from .db import close_db, init_db
from .errors import api_error

CSRF_EXEMPT = ("/api/rsvp/", "/api/payments/razorpay/webhook")
CSRF_HEADER_VALUE = "urlovingly"


def create_app(overrides=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(load_config(overrides))

    if app.config["ENV"] != "development":
        if app.config["PAYMENT_PROVIDER"] != "razorpay":
            raise RuntimeError("Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET (or run with URLOVINGLY_ENV=development).")
        if app.config["ALLOW_DEV_LOGIN"]:
            raise RuntimeError("Developer login is only allowed with URLOVINGLY_ENV=development.")

    init_db(app.config["DATABASE"])
    app.extensions["payment_provider"] = payments.build_provider(app.config)
    app.extensions["google_verifier"] = auth.default_google_verifier(app.config["GOOGLE_CLIENT_ID"])

    app.teardown_appcontext(close_db)
    for blueprint in (auth.bp, payments.bp, events.bp, owner.bp, pages.bp):
        app.register_blueprint(blueprint)

    @app.before_request
    def require_csrf_header():
        # A custom header cannot be sent cross-site without a CORS preflight, which we never allow.
        if (
            request.method in ("POST", "PUT", "PATCH", "DELETE")
            and request.path.startswith("/api/")
            and not request.path.startswith(CSRF_EXEMPT)
            and request.headers.get("X-Requested-With") != CSRF_HEADER_VALUE
        ):
            return api_error("csrf_rejected", "Missing X-Requested-With header.", 403)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    @app.errorhandler(404)
    @app.errorhandler(405)
    @app.errorhandler(413)
    def json_errors(error):
        if request.path.startswith("/api/"):
            return api_error(error.name.lower().replace(" ", "_"), error.description, error.code)
        return error

    return app
