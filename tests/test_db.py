"""
Tests for db.py — store_message, get_recent_messages (in-memory SQLite).
"""

import pytest
from datetime import datetime, timezone, timedelta
from db import init_db, store_message, get_recent_messages


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
