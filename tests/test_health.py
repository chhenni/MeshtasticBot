"""
Tests for GET /health JSON endpoint (issue #5).
"""

from datetime import datetime, timezone

import pytest

from db import init_db, store_message
from web import create_app


@pytest.fixture
def conn():
    return init_db(":memory:")


@pytest.fixture
def client(conn):
    bot_state = {"start_time": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc), "connected": True}
    app = create_app(conn, bot_state)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def client_no_state(conn):
    app = create_app(conn, {})
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestHealthEndpoint:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_content_type_is_json(self, client):
        r = client.get("/health")
        assert r.content_type == "application/json"

    def test_connected_field(self, client):
        data = client.get("/health").get_json()
        assert data["connected"] is True

    def test_uptime_seconds_is_positive(self, client):
        data = client.get("/health").get_json()
        assert data["uptime_seconds"] > 0

    def test_db_size_bytes_is_non_negative(self, client):
        data = client.get("/health").get_json()
        assert data["db_size_bytes"] >= 0

    def test_last_message_at_none_when_no_messages(self, client):
        data = client.get("/health").get_json()
        assert data["last_message_at"] is None

    def test_last_message_at_set_when_messages_exist(self, conn):
        store_message(conn, "p1", 1, "!abc", "hello", "2026-05-18T10:00:00")
        bot_state = {"start_time": datetime(2026, 1, 1, tzinfo=timezone.utc), "connected": True}
        app = create_app(conn, bot_state)
        app.config["TESTING"] = True
        with app.test_client() as c:
            data = c.get("/health").get_json()
        assert data["last_message_at"] == "2026-05-18T10:00:00"

    def test_connected_false_when_not_in_state(self, client_no_state):
        data = client_no_state.get("/health").get_json()
        assert data["connected"] is False

    def test_uptime_none_when_no_start_time(self, client_no_state):
        data = client_no_state.get("/health").get_json()
        assert data["uptime_seconds"] is None
