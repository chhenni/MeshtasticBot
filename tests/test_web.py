"""
Tests for core web routes: /, /status, /api/messages (issue #6).
/nodes is covered in test_web_nodes.py; /audit in test_audit_web.py; /health in test_health.py.
"""

from datetime import datetime, timezone

import pytest

from db import init_db, store_message, upsert_node
from web import create_app


@pytest.fixture
def conn():
    c = init_db(":memory:")
    store_message(c, "p1", 0, "!aabbccdd", "hello world", "2026-05-18T10:00:00")
    store_message(c, "p2", 1, "!eeff0011", "good morning", "2026-05-18T11:00:00")
    store_message(c, "p3", 0, "!aabbccdd", "another message", "2026-05-18T12:00:00")
    return c


@pytest.fixture
def bot_state():
    return {
        "start_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "connected": True,
        "channel": 0,
        "county": "03",
    }


@pytest.fixture
def client(conn, bot_state):
    app = create_app(conn, bot_state)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestMessageLogRoute:
    def test_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_shows_messages(self, client):
        r = client.get("/")
        assert b"hello world" in r.data
        assert b"good morning" in r.data

    def test_shows_sender_id(self, client):
        r = client.get("/")
        assert b"!aabbccdd" in r.data

    def test_filter_by_channel(self, client):
        r = client.get("/?channel=1")
        assert b"good morning" in r.data
        assert b"hello world" not in r.data

    def test_empty_db_returns_200(self, bot_state):
        conn = init_db(":memory:")
        app = create_app(conn, bot_state)
        app.config["TESTING"] = True
        with app.test_client() as c:
            assert c.get("/").status_code == 200

    def test_shows_node_long_name_when_known(self, conn, bot_state):
        upsert_node(conn, "!aabbccdd", long_name="Alice Node", short_name="ALI", last_seen="2026-05-18")
        app = create_app(conn, bot_state)
        app.config["TESTING"] = True
        with app.test_client() as c:
            r = c.get("/")
        assert b"Alice Node" in r.data

    def test_pagination_page2(self, conn, bot_state):
        # Add enough messages to force pagination (PAGE_SIZE=50)
        for i in range(50):
            store_message(conn, f"px{i}", 0, "!abc", f"msg {i}", f"2026-05-18T13:{i:02d}:00")
        app = create_app(conn, bot_state)
        app.config["TESTING"] = True
        with app.test_client() as c:
            r = c.get("/?page=2")
        assert r.status_code == 200


class TestStatusRoute:
    def test_returns_200(self, client):
        assert client.get("/status").status_code == 200

    def test_shows_page_heading(self, client):
        r = client.get("/status")
        assert b"Bot Status" in r.data

    def test_shows_message_counts(self, client):
        r = client.get("/status")
        assert b"3" in r.data  # total message count

    def test_shows_start_time(self, client):
        r = client.get("/status")
        assert b"2026-01-01" in r.data

    def test_empty_bot_state_does_not_crash(self, conn):
        app = create_app(conn, {})
        app.config["TESTING"] = True
        with app.test_client() as c:
            assert c.get("/status").status_code == 200


class TestApiMessagesRoute:
    def test_returns_200(self, client):
        assert client.get("/api/messages").status_code == 200

    def test_returns_json(self, client):
        r = client.get("/api/messages")
        assert r.content_type == "application/json"

    def test_response_has_expected_keys(self, client):
        data = client.get("/api/messages").get_json()
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "messages" in data

    def test_total_matches_message_count(self, client):
        data = client.get("/api/messages").get_json()
        assert data["total"] == 3

    def test_filter_by_channel(self, client):
        data = client.get("/api/messages?channel=1").get_json()
        assert data["total"] == 1
        assert data["messages"][0]["text"] == "good morning"

    def test_messages_include_sender_id(self, client):
        data = client.get("/api/messages").get_json()
        senders = {m["sender_id"] for m in data["messages"]}
        assert "!aabbccdd" in senders

    def test_page_param(self, client):
        data = client.get("/api/messages?page=1").get_json()
        assert data["page"] == 1

    def test_invalid_page_defaults_to_1(self, client):
        data = client.get("/api/messages?page=abc").get_json()
        assert data["page"] == 1

    def test_empty_db_returns_zero_total(self, bot_state):
        conn = init_db(":memory:")
        app = create_app(conn, bot_state)
        app.config["TESTING"] = True
        with app.test_client() as c:
            data = c.get("/api/messages").get_json()
        assert data["total"] == 0
        assert data["messages"] == []
