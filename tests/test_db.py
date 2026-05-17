"""
Tests for db.py — store_message, get_recent_messages (in-memory SQLite).
"""

from datetime import datetime, timedelta, timezone

import pytest

from db import get_recent_messages, init_db, purge_old_messages, store_message


@pytest.fixture
def conn():
    return init_db(":memory:")


class TestStoreAndRetrieve:
    def test_stored_message_is_returned(self, conn):
        now = datetime.now(tz=timezone.utc).isoformat()
        store_message(conn, "id1", 1, "!abc", "Hello", now)
        rows = get_recent_messages(conn, 1, 24)
        assert len(rows) == 1
        assert rows[0]["text"] == "Hello"
        assert rows[0]["sender_id"] == "!abc"

    def test_multiple_messages_all_returned(self, conn):
        now = datetime.now(tz=timezone.utc).isoformat()
        for i in range(5):
            store_message(conn, f"id{i}", 1, "!abc", f"Message {i}", now)
        assert len(get_recent_messages(conn, 1, 24)) == 5

    def test_dedup_by_packet_id(self, conn):
        now = datetime.now(tz=timezone.utc).isoformat()
        store_message(conn, "same-id", 1, "!abc", "First", now)
        store_message(conn, "same-id", 1, "!abc", "Second", now)
        rows = get_recent_messages(conn, 1, 24)
        assert len(rows) == 1
        assert rows[0]["text"] == "First"

    def test_channel_isolation(self, conn):
        now = datetime.now(tz=timezone.utc).isoformat()
        store_message(conn, "id1", 1, "!abc", "On channel 1", now)
        store_message(conn, "id2", 2, "!abc", "On channel 2", now)
        assert len(get_recent_messages(conn, 1, 24)) == 1
        assert len(get_recent_messages(conn, 2, 24)) == 1

    def test_time_window_excludes_old_messages(self, conn):
        old = (datetime.now(tz=timezone.utc) - timedelta(hours=48)).isoformat()
        recent = datetime.now(tz=timezone.utc).isoformat()
        store_message(conn, "old", 1, "!abc", "Old message", old)
        store_message(conn, "new", 1, "!abc", "Recent message", recent)
        rows = get_recent_messages(conn, 1, 24)
        assert len(rows) == 1
        assert rows[0]["text"] == "Recent message"

    def test_returned_in_ascending_order(self, conn):
        base = datetime.now(tz=timezone.utc)
        for i in range(3):
            ts = (base + timedelta(seconds=i)).isoformat()
            store_message(conn, f"id{i}", 1, "!abc", f"msg{i}", ts)
        rows = get_recent_messages(conn, 1, 24)
        texts = [r["text"] for r in rows]
        assert texts == ["msg0", "msg1", "msg2"]

    def test_empty_channel_returns_empty_list(self, conn):
        assert get_recent_messages(conn, 99, 24) == []


class TestPurgeOldMessages:
    def test_purge_removes_old_rows(self, conn):
        old = (datetime.now(tz=timezone.utc) - timedelta(days=400)).isoformat()
        store_message(conn, "old", 1, "!abc", "Old", old)
        deleted = purge_old_messages(conn, days=365)
        assert deleted == 1
        assert get_recent_messages(conn, 1, 24 * 400) == []

    def test_purge_keeps_recent_rows(self, conn):
        recent = datetime.now(tz=timezone.utc).isoformat()
        store_message(conn, "recent", 1, "!abc", "Recent", recent)
        deleted = purge_old_messages(conn, days=365)
        assert deleted == 0
        assert len(get_recent_messages(conn, 1, 24)) == 1

    def test_purge_only_removes_old(self, conn):
        old = (datetime.now(tz=timezone.utc) - timedelta(days=400)).isoformat()
        recent = datetime.now(tz=timezone.utc).isoformat()
        store_message(conn, "old", 1, "!abc", "Old", old)
        store_message(conn, "new", 1, "!abc", "Recent", recent)
        deleted = purge_old_messages(conn, days=365)
        assert deleted == 1
        rows = get_recent_messages(conn, 1, 24)
        assert rows[0]["text"] == "Recent"

    def test_purge_returns_zero_on_empty_db(self, conn):
        assert purge_old_messages(conn, days=365) == 0


class TestDatabaseSettings:
    def test_wal_mode_enabled(self, tmp_path):
        """init_db should enable WAL journal mode for thread-safe concurrent access."""
        import db as db_module
        conn = db_module.init_db(str(tmp_path / "test.db"))
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"

    def test_timeout_allows_retry_on_busy(self, tmp_path):
        """Connection should have a non-zero busy timeout so threads retry on SQLITE_BUSY."""
        import db as db_module
        conn = db_module.init_db(str(tmp_path / "test.db"))
        row = conn.execute("PRAGMA busy_timeout").fetchone()
        assert row[0] > 0

    def test_wal_not_set_for_memory_db(self):
        """In-memory DBs used in tests don't need WAL (it's silently ignored)."""
        conn = init_db(":memory:")
        # :memory: with WAL silently falls back to 'memory' mode — just check no crash
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] in ("wal", "memory")

