"""
Tests for the node registry DB functions: upsert_node, get_node, lookup_nodes_by_name.
"""


import pytest

from db import get_node, init_db, lookup_nodes_by_name, upsert_node


@pytest.fixture
def conn():
    return init_db(":memory:")


TS = "2026-05-18T00:00:00+00:00"


class TestUpsertNode:
    def test_insert_new_node(self, conn):
        upsert_node(conn, "!abc", long_name="Alpha", last_seen=TS)
        node = get_node(conn, "!abc")
        assert node is not None
        assert node["node_id"] == "!abc"
        assert node["long_name"] == "Alpha"

    def test_update_existing_node(self, conn):
        upsert_node(conn, "!abc", long_name="Old Name", last_seen=TS)
        ts2 = "2026-05-18T01:00:00+00:00"
        upsert_node(conn, "!abc", long_name="New Name", last_seen=ts2)
        node = get_node(conn, "!abc")
        assert node["long_name"] == "New Name"
        assert node["last_seen"] == ts2

    def test_stores_snr_and_rssi(self, conn):
        upsert_node(conn, "!abc", last_seen=TS, snr=7.5, rssi=-85)
        node = get_node(conn, "!abc")
        assert node["last_snr"] == 7.5
        assert node["last_rssi"] == -85

    def test_stores_position(self, conn):
        upsert_node(conn, "!abc", last_seen=TS, lat=59.9139, lon=10.7522)
        node = get_node(conn, "!abc")
        assert abs(node["lat"] - 59.9139) < 0.0001
        assert abs(node["lon"] - 10.7522) < 0.0001

    def test_partial_update_preserves_existing_fields(self, conn):
        upsert_node(conn, "!abc", long_name="Alpha", last_seen=TS, snr=5.0)
        upsert_node(conn, "!abc", last_seen=TS, snr=8.0)
        node = get_node(conn, "!abc")
        assert node["long_name"] == "Alpha"
        assert node["last_snr"] == 8.0


class TestGetNode:
    def test_returns_none_for_unknown_id(self, conn):
        assert get_node(conn, "!unknown") is None

    def test_returns_dict_with_all_fields(self, conn):
        upsert_node(conn, "!abc", long_name="Alpha", short_name="AL",
                    last_seen=TS, snr=4.0, rssi=-90, lat=59.0, lon=10.0)
        node = get_node(conn, "!abc")
        for field in ("node_id", "long_name", "short_name", "last_seen",
                      "last_snr", "last_rssi", "lat", "lon"):
            assert field in node


class TestLookupNodesByName:
    def test_exact_long_name_match(self, conn):
        upsert_node(conn, "!abc", long_name="Alpha Node", last_seen=TS)
        results = lookup_nodes_by_name(conn, "Alpha Node")
        assert len(results) == 1
        assert results[0]["node_id"] == "!abc"

    def test_partial_long_name_match(self, conn):
        upsert_node(conn, "!abc", long_name="Alpha Node", last_seen=TS)
        results = lookup_nodes_by_name(conn, "alpha")
        assert len(results) == 1

    def test_short_name_match(self, conn):
        upsert_node(conn, "!abc", short_name="AL", last_seen=TS)
        results = lookup_nodes_by_name(conn, "al")
        assert len(results) == 1

    def test_multiple_matches(self, conn):
        upsert_node(conn, "!a", long_name="Alpha One", last_seen=TS)
        upsert_node(conn, "!b", long_name="Alpha Two", last_seen=TS)
        results = lookup_nodes_by_name(conn, "alpha")
        assert len(results) == 2

    def test_no_match_returns_empty(self, conn):
        upsert_node(conn, "!abc", long_name="Alpha", last_seen=TS)
        assert lookup_nodes_by_name(conn, "bravo") == []

    def test_case_insensitive(self, conn):
        upsert_node(conn, "!abc", long_name="UPPER CASE", last_seen=TS)
        assert len(lookup_nodes_by_name(conn, "upper")) == 1
        assert len(lookup_nodes_by_name(conn, "UPPER")) == 1
