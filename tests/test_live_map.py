"""
Tests for live updates (SSE) and map view (issue #11).
"""

from datetime import datetime, timezone

import pytest

from db import init_db, store_message, upsert_node
from web import create_app, push_event


@pytest.fixture
def conn():
    c = init_db(":memory:")
    upsert_node(c, "!aabb", long_name="Alice", short_name="ALI",
                last_seen="2026-05-18T10:00:00", lat=59.9, lon=10.7)
    upsert_node(c, "!ccdd", long_name="Bob", short_name="BOB",
                last_seen="2026-05-18T11:00:00", lat=None, lon=None)
    store_message(c, "p1", 0, "!aabb", "hello", "2026-05-18T10:00:00")
    return c


@pytest.fixture
def bot_state():
    return {"start_time": datetime(2026, 1, 1, tzinfo=timezone.utc), "connected": True}


@pytest.fixture
def client(conn, bot_state):
    app = create_app(conn, bot_state)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestApiNodesEndpoint:
    def test_returns_200(self, client):
        assert client.get("/api/nodes").status_code == 200

    def test_returns_json(self, client):
        r = client.get("/api/nodes")
        assert r.content_type == "application/json"

    def test_response_has_nodes_key(self, client):
        data = client.get("/api/nodes").get_json()
        assert "nodes" in data

    def test_nodes_include_expected_fields(self, client):
        data = client.get("/api/nodes").get_json()
        node = next(n for n in data["nodes"] if n["node_id"] == "!aabb")
        assert "node_id" in node
        assert "long_name" in node
        assert "lat" in node
        assert "lon" in node

    def test_nodes_with_position_have_lat_lon(self, client):
        data = client.get("/api/nodes").get_json()
        alice = next(n for n in data["nodes"] if n["node_id"] == "!aabb")
        assert alice["lat"] == pytest.approx(59.9)
        assert alice["lon"] == pytest.approx(10.7)

    def test_nodes_without_position_have_none(self, client):
        data = client.get("/api/nodes").get_json()
        bob = next(n for n in data["nodes"] if n["node_id"] == "!ccdd")
        assert bob["lat"] is None
        assert bob["lon"] is None

    def test_empty_db_returns_empty_list(self, bot_state):
        conn = init_db(":memory:")
        app = create_app(conn, bot_state)
        app.config["TESTING"] = True
        with app.test_client() as c:
            data = c.get("/api/nodes").get_json()
        assert data["nodes"] == []


class TestMapRoute:
    def test_returns_200(self, client):
        assert client.get("/map").status_code == 200

    def test_contains_leaflet(self, client):
        r = client.get("/map")
        assert b"leaflet" in r.data.lower()

    def test_contains_map_div(self, client):
        r = client.get("/map")
        assert b'id="map"' in r.data

    def test_nav_link_present_on_logs_page(self, client):
        r = client.get("/")
        assert b"/map" in r.data


class TestSseEvents:
    def test_push_event_sends_to_queue(self):
        import queue as qmodule

        from web import push_event
        q = qmodule.SimpleQueue()

        import web
        web._sse_clients.append(q)
        try:
            push_event("message", {"text": "hello", "channel": 0})
            item = q.get_nowait()
            assert "message" in item
            assert "hello" in item
        finally:
            try:
                web._sse_clients.remove(q)
            except ValueError:
                pass

    def test_push_event_removes_dead_clients(self):
        import web

        class _BadQueue:
            def put_nowait(self, _):
                raise RuntimeError("dead")

        bad = _BadQueue()
        web._sse_clients.append(bad)
        push_event("test", {})  # should not raise, should remove bad queue
        assert bad not in web._sse_clients

    def test_sse_endpoint_content_type(self, client):
        # Use a short-circuit: just check the response starts streaming
        r = client.get("/api/events", headers={"Accept": "text/event-stream"})
        assert "text/event-stream" in r.content_type
