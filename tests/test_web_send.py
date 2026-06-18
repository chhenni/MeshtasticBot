"""
Tests for admin send-message endpoints: GET /admin/send, POST /admin/send, POST /api/send.
"""

import base64

import pytest

from db import init_db, store_message, upsert_node
from web import create_app

ADMIN_USER = "admin"
ADMIN_PASS = "testpass"


def auth_header(username=ADMIN_USER, password=ADMIN_PASS):
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


class MockInterface:
    """Minimal stub that records sendText calls."""

    def __init__(self):
        self.calls = []

    def sendText(self, text, **kwargs):
        self.calls.append({"text": text, **kwargs})


def _make_send_fn(interface):
    """Capture calls without retry logic for test simplicity."""
    def send_fn(iface, text, **kwargs):
        iface.sendText(text, **kwargs)
    return send_fn


@pytest.fixture
def conn():
    c = init_db(":memory:")
    store_message(c, "p1", 2, "!aabbccdd", "hello mesh", "2026-06-01T10:00:00")
    store_message(c, "p2", -1, "!aabbccdd", "private dm", "2026-06-01T10:01:00")
    upsert_node(c, "!aabbccdd", long_name="Alice", short_name="ALI", last_seen="2026-06-01")
    return c


@pytest.fixture
def mock_iface():
    return MockInterface()


@pytest.fixture
def client(conn, mock_iface):
    bot_state = {
        "interface": mock_iface,
        "send_fn": _make_send_fn(mock_iface),
        "channel": 2,
        "log_channel": 2,
        "county": None,
        "start_time": None,
    }
    app = create_app(conn, bot_state, admin_username=ADMIN_USER, admin_password=ADMIN_PASS)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ── Auth ─────────────────────────────────────────────────────────────────────

class TestSendAuth:
    def test_get_requires_auth(self, client):
        assert client.get("/admin/send").status_code == 401

    def test_get_wrong_password_rejected(self, client):
        assert client.get("/admin/send", headers=auth_header(password="bad")).status_code == 401

    def test_get_accepted_with_correct_credentials(self, client):
        assert client.get("/admin/send", headers=auth_header()).status_code == 200

    def test_post_requires_auth(self, client):
        assert client.post("/admin/send").status_code == 401

    def test_api_send_requires_auth(self, client):
        assert client.post("/api/send", json={"text": "hi", "channel": 0}).status_code == 401


# ── GET /admin/send ───────────────────────────────────────────────────────────

class TestSendPage:
    def test_shows_compose_form(self, client):
        r = client.get("/admin/send", headers=auth_header())
        assert b"compose-form" in r.data

    def test_shows_known_nodes_in_datalist(self, client):
        r = client.get("/admin/send", headers=auth_header())
        assert b"!aabbccdd" in r.data

    def test_channel_history_shown_when_channel_param(self, client):
        r = client.get("/admin/send?channel=2", headers=auth_header())
        assert b"hello mesh" in r.data

    def test_dm_history_shown_when_node_param(self, client):
        r = client.get("/admin/send?node=!aabbccdd", headers=auth_header())
        assert b"private dm" in r.data

    def test_no_history_without_context_param(self, client):
        r = client.get("/admin/send", headers=auth_header())
        assert b"hello mesh" not in r.data
        assert b"private dm" not in r.data

    def test_flash_message_displayed(self, client):
        r = client.get("/admin/send?flash=All+good&flash_type=success", headers=auth_header())
        assert b"All good" in r.data


# ── POST /admin/send ──────────────────────────────────────────────────────────

class TestSendPost:
    def test_channel_send_redirects(self, client):
        r = client.post(
            "/admin/send",
            data={"text": "test msg", "target_type": "channel", "channel_index": "2"},
            headers=auth_header(),
        )
        assert r.status_code in (301, 302)

    def test_channel_send_calls_interface(self, client, mock_iface):
        client.post(
            "/admin/send",
            data={"text": "test msg", "target_type": "channel", "channel_index": "2"},
            headers=auth_header(),
        )
        assert len(mock_iface.calls) == 1
        assert mock_iface.calls[0]["text"] == "test msg"
        assert mock_iface.calls[0].get("channelIndex") == 2

    def test_dm_send_calls_interface(self, client, mock_iface):
        client.post(
            "/admin/send",
            data={"text": "hello!", "target_type": "node", "destination_id": "!aabbccdd"},
            headers=auth_header(),
        )
        assert len(mock_iface.calls) == 1
        assert mock_iface.calls[0]["text"] == "hello!"
        assert mock_iface.calls[0].get("destinationId") == "!aabbccdd"
        assert mock_iface.calls[0].get("channelIndex") == 0

    def test_missing_text_returns_400(self, client):
        r = client.post(
            "/admin/send",
            data={"text": "", "target_type": "channel", "channel_index": "0"},
            headers=auth_header(),
        )
        assert r.status_code == 400

    def test_channel_redirect_contains_channel_param(self, client):
        r = client.post(
            "/admin/send",
            data={"text": "hi", "target_type": "channel", "channel_index": "3"},
            headers=auth_header(),
        )
        assert "channel=3" in r.headers.get("Location", "")

    def test_dm_redirect_contains_node_param(self, client):
        r = client.post(
            "/admin/send",
            data={"text": "hi", "target_type": "node", "destination_id": "!aabbccdd"},
            headers=auth_header(),
        )
        assert "node=!aabbccdd" in r.headers.get("Location", "")

    def test_send_error_redirects_with_error_flash(self, conn):
        """If the send_fn raises, the redirect should carry a danger flash."""
        def failing_send(iface, text, **kwargs):
            raise RuntimeError("device busy")

        bot_state = {
            "interface": MockInterface(),
            "send_fn": failing_send,
            "channel": 0,
            "log_channel": 0,
            "county": None,
            "start_time": None,
        }
        app = create_app(conn, bot_state, admin_username=ADMIN_USER, admin_password=ADMIN_PASS)
        app.config["TESTING"] = True
        with app.test_client() as c:
            r = c.post(
                "/admin/send",
                data={"text": "hi", "target_type": "channel", "channel_index": "0"},
                headers=auth_header(),
            )
        assert r.status_code in (301, 302)
        assert "danger" in r.headers.get("Location", "")

    def test_no_interface_redirects_with_error_flash(self, conn):
        bot_state = {"interface": None, "send_fn": None}
        app = create_app(conn, bot_state, admin_username=ADMIN_USER, admin_password=ADMIN_PASS)
        app.config["TESTING"] = True
        with app.test_client() as c:
            r = c.post(
                "/admin/send",
                data={"text": "hi", "target_type": "channel", "channel_index": "0"},
                headers=auth_header(),
            )
        assert r.status_code in (301, 302)
        assert "danger" in r.headers.get("Location", "")


# ── POST /api/send ────────────────────────────────────────────────────────────

class TestApiSend:
    def test_channel_send_returns_json(self, client, mock_iface):
        r = client.post(
            "/api/send",
            json={"text": "api test", "channel": 1},
            headers=auth_header(),
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "sent"
        assert data["channel"] == 1

    def test_dm_send_returns_json(self, client, mock_iface):
        r = client.post(
            "/api/send",
            json={"text": "dm test", "destination_id": "!aabbccdd"},
            headers=auth_header(),
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "sent"
        assert data["destination_id"] == "!aabbccdd"

    def test_missing_text_returns_400(self, client):
        r = client.post("/api/send", json={"channel": 0}, headers=auth_header())
        assert r.status_code == 400

    def test_missing_target_returns_400(self, client):
        r = client.post("/api/send", json={"text": "hi"}, headers=auth_header())
        assert r.status_code == 400

    def test_no_interface_returns_503(self, conn):
        bot_state = {"interface": None, "send_fn": None}
        app = create_app(conn, bot_state, admin_username=ADMIN_USER, admin_password=ADMIN_PASS)
        app.config["TESTING"] = True
        with app.test_client() as c:
            r = c.post("/api/send", json={"text": "hi", "channel": 0}, headers=auth_header())
        assert r.status_code == 503

    def test_channel_send_calls_interface(self, client, mock_iface):
        client.post("/api/send", json={"text": "hello api", "channel": 5}, headers=auth_header())
        assert len(mock_iface.calls) == 1
        assert mock_iface.calls[0]["channelIndex"] == 5
