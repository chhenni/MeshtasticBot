"""
Tests for handle_krslog_command in main.py.
Uses in-memory SQLite and a simple reply collector instead of a real interface.
"""

import pytest
from datetime import datetime, timezone, timedelta
from db import init_db, store_message
from commands import handle_krslog_command
from constants import MAX_BYTES, MAX_KRSLOG_HOURS


@pytest.fixture
def conn():
    return init_db(":memory:")


def collect_replies(conn, text, log_channel=1):
    """Call handle_krslog_command and collect all reply strings."""
    replies = []
    ctx = {"db_conn": conn, "log_channel": log_channel, "interface": None, "sender": None}
    handle_krslog_command(text, replies.append, ctx)
    return replies


def store_n(conn, n, channel=1, text_fn=None):
    base = datetime.now(tz=timezone.utc)
    for i in range(n):
        ts = (base + timedelta(seconds=i)).isoformat()
        msg = text_fn(i) if text_fn else f"Message {i}"
        store_message(conn, f"id{i}", channel, "!abc", msg, ts)


class TestKrslogCommand:
    def test_no_messages_returns_info(self, conn):
        replies = collect_replies(conn, "/krslog")
        assert len(replies) == 1
        assert "Ingen" in replies[0]

    def test_disabled_db_returns_info(self):
        replies = []
        ctx = {"db_conn": None, "log_channel": 1, "interface": None, "sender": None}
        handle_krslog_command("/krslog", replies.append, ctx)
        assert "ikke aktivert" in replies[0]

    def test_single_message_no_counter(self, conn):
        store_n(conn, 1)
        replies = collect_replies(conn, "/krslog")
        assert len(replies) == 1
        assert not replies[0].startswith("[")

    def test_many_messages_all_appear(self, conn):
        store_n(conn, 10)
        replies = collect_replies(conn, "/krslog")
        combined = "\n".join(replies)
        for i in range(10):
            assert f"Message {i}" in combined

    def test_all_pages_within_byte_limit(self, conn):
        store_n(conn, 20)
        for msg in collect_replies(conn, "/krslog"):
            assert len(msg.encode("utf-8")) <= MAX_BYTES

    def test_multi_page_has_counter(self, conn):
        store_n(conn, 20, text_fn=lambda i: "A" * 50)
        replies = collect_replies(conn, "/krslog")
        if len(replies) > 1:
            assert replies[0].startswith("[1/")

    def test_custom_hour_window(self, conn):
        old = (datetime.now(tz=timezone.utc) - timedelta(hours=50)).isoformat()
        store_message(conn, "old", 1, "!abc", "Old message", old)
        store_n(conn, 2)
        replies = collect_replies(conn, "/krslog 24")
        combined = "\n".join(replies)
        assert "Old message" not in combined
        assert "Message 0" in combined

    def test_invalid_hours_returns_error(self, conn):
        replies = collect_replies(conn, "/krslog abc")
        assert "Bruk:" in replies[0]

    def test_zero_hours_returns_error(self, conn):
        replies = collect_replies(conn, "/krslog 0")
        assert "Bruk:" in replies[0]

    def test_over_limit_is_clamped(self, conn):
        store_n(conn, 3)
        over = MAX_KRSLOG_HOURS + 100
        replies = collect_replies(conn, f"/krslog {over}")
        # First reply should be the clamping notice
        assert str(MAX_KRSLOG_HOURS) in replies[0]
        # Messages still returned (second reply onward)
        combined = "\n".join(replies[1:])
        assert "Message 0" in combined
