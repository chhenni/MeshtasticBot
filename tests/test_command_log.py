"""
Tests for command audit log DB layer.
"""

from datetime import datetime, timezone

import pytest

from db import get_command_log, init_db, log_command


@pytest.fixture
def conn():
    return init_db(":memory:")


class TestLogCommand:
    def test_log_ok_command(self, conn):
        log_command(conn, "!abc", "/ping", "ok")
        rows = get_command_log(conn)
        assert len(rows) == 1
        assert rows[0]["node_id"] == "!abc"
        assert rows[0]["command"] == "/ping"
        assert rows[0]["status"] == "ok"

    def test_log_rate_limited_command(self, conn):
        log_command(conn, "!abc", "/weather", "rate_limited")
        rows = get_command_log(conn)
        assert rows[0]["status"] == "rate_limited"

    def test_log_banned_command(self, conn):
        log_command(conn, "!bad", "/ping", "banned")
        rows = get_command_log(conn)
        assert rows[0]["status"] == "banned"

    def test_timestamp_is_stored(self, conn):
        ts = datetime.now(timezone.utc).isoformat()
        log_command(conn, "!abc", "/ping", "ok", timestamp=ts)
        rows = get_command_log(conn)
        assert rows[0]["timestamp"] == ts

    def test_multiple_entries_returned_newest_first(self, conn):
        log_command(conn, "!abc", "/ping", "ok", timestamp="2026-05-18T00:00:00")
        log_command(conn, "!abc", "/weather", "ok", timestamp="2026-05-18T00:01:00")
        rows = get_command_log(conn)
        assert rows[0]["command"] == "/weather"
        assert rows[1]["command"] == "/ping"

    def test_filter_by_node_id(self, conn):
        log_command(conn, "!abc", "/ping", "ok")
        log_command(conn, "!xyz", "/ping", "ok")
        rows = get_command_log(conn, node_id="!abc")
        assert all(r["node_id"] == "!abc" for r in rows)
        assert len(rows) == 1

    def test_filter_by_command(self, conn):
        log_command(conn, "!abc", "/ping", "ok")
        log_command(conn, "!abc", "/weather", "ok")
        rows = get_command_log(conn, command="/ping")
        assert all(r["command"] == "/ping" for r in rows)

    def test_limit_is_respected(self, conn):
        for i in range(10):
            log_command(conn, "!abc", "/ping", "ok")
        rows = get_command_log(conn, limit=5)
        assert len(rows) == 5

    def test_empty_log_returns_empty_list(self, conn):
        assert get_command_log(conn) == []
