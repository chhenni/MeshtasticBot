"""
Tests for the POST /api/command endpoint (Basic Auth protected).
"""

import base64
from unittest.mock import patch

import pytest

from db import init_db
from web import create_app

ADMIN_USER = "admin"
ADMIN_PASS = "testpass"


def auth_header(username=ADMIN_USER, password=ADMIN_PASS):
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def conn():
    return init_db(":memory:")


@pytest.fixture
def bot_state():
    return {
        "interface": None,
        "channel": 0,
        "log_channel": 0,
        "county": "42",
        "start_time": None,
        "flipper_cfg": None,
        "connected": True,
    }


@pytest.fixture
def client(conn, bot_state):
    app = create_app(
        conn,
        bot_state,
        admin_username=ADMIN_USER,
        admin_password=ADMIN_PASS,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestApiCommandAuth:
    def test_requires_auth_no_credentials(self, client):
        resp = client.post("/api/command", json={"command": "/ping"})
        assert resp.status_code == 401

    def test_requires_auth_wrong_password(self, client):
        resp = client.post(
            "/api/command",
            json={"command": "/ping"},
            headers=auth_header(password="wrong"),
        )
        assert resp.status_code == 401

    def test_valid_credentials_accepted(self, client):
        resp = client.post(
            "/api/command",
            json={"command": "/ping"},
            headers=auth_header(),
        )
        assert resp.status_code == 200


class TestApiCommandErrors:
    def test_missing_command_field(self, client):
        resp = client.post("/api/command", json={}, headers=auth_header())
        assert resp.status_code == 400
        assert "Missing command" in resp.get_json()["error"]

    def test_empty_command_string(self, client):
        resp = client.post("/api/command", json={"command": ""}, headers=auth_header())
        assert resp.status_code == 400

    def test_unknown_command(self, client):
        resp = client.post(
            "/api/command",
            json={"command": "/notarealcommand"},
            headers=auth_header(),
        )
        assert resp.status_code == 400
        assert "Unknown command" in resp.get_json()["error"]

    def test_invalid_lat_lon(self, client):
        resp = client.post(
            "/api/command",
            json={"command": "/weather", "lat": "not-a-number", "lon": 7.9},
            headers=auth_header(),
        )
        assert resp.status_code == 400


class TestApiCommandPing:
    def test_ping_returns_replies(self, client):
        resp = client.post(
            "/api/command",
            json={"command": "/ping"},
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["command"] == "/ping"
        assert isinstance(data["replies"], list)
        assert len(data["replies"]) >= 1

    def test_ping_response_contains_pong(self, client):
        resp = client.post(
            "/api/command",
            json={"command": "/ping"},
            headers=auth_header(),
        )
        combined = " ".join(resp.get_json()["replies"])
        assert "pong" in combined.lower() or "🟢" in combined or "Pong" in combined


class TestApiCommandHelp:
    def test_help_returns_multiple_replies(self, client):
        resp = client.post(
            "/api/command",
            json={"command": "/help"},
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["replies"]) > 1


class TestApiCommandWeather:
    def test_weather_without_coords_returns_error(self, client):
        resp = client.post(
            "/api/command",
            json={"command": "/weather"},
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        combined = " ".join(data["replies"])
        assert "GPS" in combined or "posisjon" in combined.lower()

    def test_weather_with_coords(self, client):
        fake_forecast = [
            {
                "date": __import__("datetime").date(2099, 6, 1),
                "day_name": "Man",
                "temp_min": 10,
                "temp_max": 18,
                "precip": 0.0,
                "symbol": "☀️ Sol",
                "wind": 3.5,
            }
        ]
        with patch("commands.get_forecast", return_value=fake_forecast):
            resp = client.post(
                "/api/command",
                json={"command": "/weather", "lat": 58.1234, "lon": 7.9876},
                headers=auth_header(),
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["replies"], list)
        assert len(data["replies"]) >= 1
        combined = " ".join(data["replies"])
        assert "58.12" in combined or "Man" in combined


class TestApiCommandAlert:
    def test_alert_no_active_alerts(self, client):
        with (
            patch("commands.get_lightning_alerts", return_value=[]),
            patch("commands.get_wind_alerts", return_value=[]),
        ):
            resp = client.post(
                "/api/command",
                json={"command": "/alert"},
                headers=auth_header(),
            )
        assert resp.status_code == 200
        combined = " ".join(resp.get_json()["replies"])
        assert "Ingen" in combined or "varsler" in combined.lower()


class TestApiCommandPrivileged:
    def test_privileged_command_allowed_via_api(self, client, conn):
        """Admin API auth is sufficient to run privileged commands."""
        from db import add_privileged_node
        add_privileged_node(conn, "!existing", added_by="test")

        resp = client.post(
            "/api/command",
            json={"command": "/removepriv !existing"},
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["replies"], list)
