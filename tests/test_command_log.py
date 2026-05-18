"""
Tests for command audit log DB layer.
"""

from datetime import datetime, timezone

import pytest

from db import get_command_log, init_db, log_command, upsert_node


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


class TestGetNodeCommandSummary:
    """Tests for get_node_command_summary() — per-node aggregated stats."""

    @pytest.fixture
    def conn(self):
        c = init_db(":memory:")
        yield c
        c.close()

    def _log(self, conn, node_id, command, status, timestamp):
        from db import log_command
        log_command(conn, node_id, command, status, timestamp=timestamp)

    def test_empty_returns_empty_list(self, conn):
        from db import get_node_command_summary
        assert get_node_command_summary(conn) == []

    def test_single_node_totals(self, conn):
        from db import get_node_command_summary
        self._log(conn, "!aaa", "/ping", "ok", "2025-01-10T10:00:00")
        self._log(conn, "!aaa", "/weather", "ok", "2025-01-10T11:00:00")
        rows = get_node_command_summary(conn)
        assert len(rows) == 1
        assert rows[0]["node_id"] == "!aaa"
        assert rows[0]["total"] == 2

    def test_rate_limited_count(self, conn):
        from db import get_node_command_summary
        self._log(conn, "!bbb", "/ping", "ok", "2025-01-10T10:00:00")
        self._log(conn, "!bbb", "/weather", "rate_limited", "2025-01-10T10:01:00")
        self._log(conn, "!bbb", "/weather", "rate_limited", "2025-01-10T10:02:00")
        rows = get_node_command_summary(conn)
        assert rows[0]["rate_limited"] == 2

    def test_today_and_week_counts(self, conn):
        from datetime import datetime, timedelta, timezone

        from db import get_node_command_summary
        now = datetime.now(timezone.utc)
        today = now.isoformat()
        three_days_ago = (now - timedelta(days=3)).isoformat()
        ten_days_ago = (now - timedelta(days=10)).isoformat()
        self._log(conn, "!ccc", "/ping", "ok", today)
        self._log(conn, "!ccc", "/ping", "ok", three_days_ago)
        self._log(conn, "!ccc", "/ping", "ok", ten_days_ago)
        rows = get_node_command_summary(conn)
        assert rows[0]["total"] == 3
        assert rows[0]["today"] == 1
        assert rows[0]["week"] == 2

    def test_sorted_by_total_descending(self, conn):
        from db import get_node_command_summary
        for _ in range(3):
            self._log(conn, "!heavy", "/ping", "ok", "2025-01-10T10:00:00")
        self._log(conn, "!light", "/ping", "ok", "2025-01-10T10:00:00")
        rows = get_node_command_summary(conn)
        assert rows[0]["node_id"] == "!heavy"

    def test_multiple_nodes_all_appear(self, conn):
        from db import get_node_command_summary
        self._log(conn, "!n1", "/ping", "ok", "2025-01-10T10:00:00")
        self._log(conn, "!n2", "/ping", "ok", "2025-01-10T10:00:00")
        self._log(conn, "!n3", "/ping", "ok", "2025-01-10T10:00:00")
        rows = get_node_command_summary(conn)
        assert len(rows) == 3

    def test_last_seen_is_most_recent(self, conn):
        from db import get_node_command_summary
        self._log(conn, "!ddd", "/ping", "ok", "2025-01-10T08:00:00")
        self._log(conn, "!ddd", "/ping", "ok", "2025-01-10T12:00:00")
        rows = get_node_command_summary(conn)
        assert rows[0]["last_seen"].startswith("2025-01-10T12")


class TestNodeNamesInAudit:
    """Tests that audit functions include long_name/short_name from nodes table."""

    @pytest.fixture
    def conn(self):
        c = init_db(":memory:")
        yield c
        c.close()

    def _log(self, conn, node_id, command="/ping", status="ok", ts="2025-01-10T10:00:00"):
        log_command(conn, node_id, command, status, timestamp=ts)

    def test_command_log_includes_node_names(self, conn):
        from db import get_command_log
        upsert_node(conn, "!abc", long_name="Alice Node", short_name="ALI", last_seen="2025-01-10")
        self._log(conn, "!abc")
        rows = get_command_log(conn)
        assert rows[0]["long_name"] == "Alice Node"
        assert rows[0]["short_name"] == "ALI"

    def test_command_log_none_for_unknown_node(self, conn):
        from db import get_command_log
        self._log(conn, "!unknown")
        rows = get_command_log(conn)
        assert rows[0]["long_name"] is None
        assert rows[0]["short_name"] is None

    def test_summary_includes_node_names(self, conn):
        from db import get_node_command_summary
        upsert_node(conn, "!abc", long_name="Alice Node", short_name="ALI", last_seen="2025-01-10")
        self._log(conn, "!abc")
        rows = get_node_command_summary(conn)
        assert rows[0]["long_name"] == "Alice Node"
        assert rows[0]["short_name"] == "ALI"

    def test_summary_none_for_unknown_node(self, conn):
        from db import get_node_command_summary
        self._log(conn, "!unknown")
        rows = get_node_command_summary(conn)
        assert rows[0]["long_name"] is None
        assert rows[0]["short_name"] is None
