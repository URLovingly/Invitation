import pytest

from server import create_app, util


class Api:
    """Thin wrapper around the Flask test client that sends the CSRF header like the real frontend."""

    def __init__(self, client):
        self.client = client

    def _headers(self, extra):
        return {"X-Requested-With": "urlovingly", **(extra or {})}

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, json=None, headers=None, **kw):
        return self.client.post(url, json=json, headers=self._headers(headers), **kw)

    def put(self, url, json=None, headers=None, **kw):
        return self.client.put(url, json=json, headers=self._headers(headers), **kw)

    def delete(self, url, headers=None, **kw):
        return self.client.delete(url, headers=self._headers(headers), **kw)

    def login(self, email="host@gmail.com", name="Host"):
        response = self.post("/api/auth/dev-login", json={"email": email, "name": name})
        assert response.status_code == 200, response.get_json()
        return self


def app_config(tmp_path, **extra):
    return {
        "ENV": "development",
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "MEDIA_DIR": str(tmp_path / "media"),
        "ALLOW_DEV_LOGIN": True,
        "PAYMENT_PROVIDER": "mock",
        "RAZORPAY_KEY_ID": "",
        "RAZORPAY_KEY_SECRET": "",
        "RAZORPAY_WEBHOOK_SECRET": "",
        "SESSION_COOKIE_SECURE": False,
        **extra,
    }


@pytest.fixture
def app(tmp_path):
    return create_app(app_config(tmp_path))


@pytest.fixture
def anon(app):
    return Api(app.test_client())


@pytest.fixture
def make_api(app):
    def factory(email="host@gmail.com", name="Host"):
        return Api(app.test_client()).login(email, name)

    return factory


@pytest.fixture
def api(make_api):
    return make_api()


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        def __init__(self):
            self.current = util.now()

        def advance(self, **delta):
            from datetime import timedelta

            self.current += timedelta(**delta)

    clock = Clock()
    monkeypatch.setattr(util, "now", lambda: clock.current)
    return clock


def create_event(api, plan, title="Aarav & Priya"):
    """Select a plan; paid plans are settled through the mock payment portal."""
    response = api.post("/api/events", json={"plan": plan, "title": title})
    assert response.status_code in (200, 201), response.get_json()
    event = response.get_json()["event"]
    if event["status"] == "pending_payment":
        pay(api, event["id"])
        event = api.get(f"/api/events/{event['id']}").get_json()["event"]
    return event


def pay(api, event_id):
    order = api.post("/api/payments/order", json={"event_id": event_id})
    assert order.status_code == 200, order.get_json()
    confirmed = api.post("/api/payments/mock-confirm", json={"order_id": order.get_json()["order_id"]})
    assert confirmed.status_code == 200, confirmed.get_json()
    return confirmed.get_json()


def invite_payload(name="Rahul Sharma", couple="Aarav & Priya", **extra):
    return {
        "name": name,
        "couple_names": couple,
        "event_type": "Wedding",
        "template": "royal",
        "rendered_html": f"<!DOCTYPE html><html><body><div class='invite-container'>Hello {name}</div></body></html>",
        **extra,
    }


def publish(api, event, **kwargs):
    return api.post(f"/api/events/{event['id']}/invites", json=invite_payload(**kwargs))
