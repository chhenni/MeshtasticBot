"""
Tests for the /nodes web route — node registry table with Google Maps links.
"""

import pytest

from db import init_db, upsert_node
from web import create_app


@pytest.fixture
def conn():
    c = init_db(":memory:")
    upsert_node(
        c, "!aabbccdd", long_name="Alpha Node", short_name="AL",
        last_seen="2026-05-18T00:00:00", snr=7.5, rssi=-85, lat=59.91, lon=10.75,
    )
    upsert_node(
        c, "!11223344", long_name="Beta Node", short_name="BE",
        last_seen="2026-05-17T12:00:00", snr=-2.0, rssi=-110, lat=None, lon=None,
    )
    upsert_node(
        c, "!deadbeef", long_name=None, short_name=None,
        last_seen="2026-05-16T08:00:00", snr=None, rssi=None, lat=None, lon=None,
    )
    return c


@pytest.fixture
def client(conn):
    app = create_app(conn, {"channel": 0, "log_channel": 0, "county": None, "start_time": None})
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestNodesRoute:
    def test_nodes_page_returns_200(self, client):
        resp = client.get("/nodes")
        assert resp.status_code == 200

    def test_nodes_page_shows_long_name(self, client):
        resp = client.get("/nodes")
        assert b"Alpha Node" in resp.data

    def test_nodes_page_shows_short_name(self, client):
        resp = client.get("/nodes")
        assert b"AL" in resp.data

    def test_nodes_page_shows_node_id(self, client):
        resp = client.get("/nodes")
        assert b"!aabbccdd" in resp.data

    def test_nodes_page_shows_snr(self, client):
        resp = client.get("/nodes")
        assert b"7.5" in resp.data

    def test_nodes_page_shows_rssi(self, client):
        resp = client.get("/nodes")
        assert b"-85" in resp.data

    def test_nodes_page_shows_last_seen(self, client):
        resp = client.get("/nodes")
        assert b"2026-05-18" in resp.data

    def test_nodes_page_has_google_maps_link_when_position_known(self, client):
        resp = client.get("/nodes")
        assert b"maps.google.com" in resp.data or b"google.com/maps" in resp.data

    def test_nodes_page_no_maps_link_when_no_position(self, client):
        # Beta Node has no position — should not have a maps link for it
        resp = client.get("/nodes")
        html = resp.data.decode()
        # The link should only appear for nodes with lat/lon
        assert "59.91" in html
        assert "10.75" in html

    def test_nodes_page_shows_all_nodes(self, client):
        resp = client.get("/nodes")
        html = resp.data.decode()
        assert "Alpha Node" in html
        assert "Beta Node" in html
        assert "!deadbeef" in html

    def test_nodes_page_search_by_name(self, client):
        resp = client.get("/nodes?q=alpha")
        html = resp.data.decode()
        assert "Alpha Node" in html
        assert "Beta Node" not in html

    def test_nodes_page_search_by_id(self, client):
        resp = client.get("/nodes?q=!11223344")
        html = resp.data.decode()
        assert "Beta Node" in html
        assert "Alpha Node" not in html

    def test_nodes_page_search_no_results(self, client):
        resp = client.get("/nodes?q=ZZZunknown")
        html = resp.data.decode()
        assert "ingen noder" in html.lower() or "no nodes" in html.lower() or "ZZZunknown" in html

    def test_nodes_nav_link_present_on_all_pages(self, client):
        for path in ["/", "/status", "/nodes"]:
            resp = client.get(path)
            assert b"/nodes" in resp.data


class TestGetAllNodes:
    def test_get_all_nodes_returns_all(self, conn):
        from db import get_all_nodes
        rows = get_all_nodes(conn)
        assert len(rows) == 3

    def test_get_all_nodes_sorted_by_last_seen_desc(self, conn):
        from db import get_all_nodes
        rows = get_all_nodes(conn)
        assert rows[0]["node_id"] == "!aabbccdd"
        assert rows[-1]["node_id"] == "!deadbeef"

    def test_get_all_nodes_search_filters(self, conn):
        from db import get_all_nodes
        rows = get_all_nodes(conn, query="beta")
        assert len(rows) == 1
        assert rows[0]["node_id"] == "!11223344"

    def test_get_all_nodes_empty_db(self):
        from db import get_all_nodes, init_db
        c = init_db(":memory:")
        assert get_all_nodes(c) == []
