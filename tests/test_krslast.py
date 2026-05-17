"""
Tests for handle_krslast_command in main.py.
Uses in-memory SQLite and a simple reply collector.
"""

from datetime import datetime, timedelta, timezone

import pytest

from commands import handle_krslast_command
from constants import MAX_BYTES, MAX_KRSLAST
from db import init_db, store_message


@pytest.fixture
def conn():
    return init_db(":memory:")


def collect_replies(conn, text, log_channel=1):
    replies = []
    ctx = {"db_conn": conn, "log_channel": log_channel, "interface": None, "sender": None}
    handle_krslast_command(text, replies.append, ctx)
    return replies


def store_n(conn, n, channel=1):
    base = datetime.now(tz=timezone.utc)
    for i in range(n):
        ts = (base + timedelta(seconds=i)).isoformat()
        store_message(conn, f"id{i}", channel, "!abc", f"Message {i}", ts)


class TestKrslastCommand:
    def test_no_messages_returns_info(self, conn):
        replies = collect_replies(conn, "/krslast")
        assert len(replies) == 1
        assert "Ingen" in replies[0]

    def test_disabled_db_returns_info(self):
        replies = []
        ctx = {"db_conn": None, "log_channel": 1, "interface": None, "sender": None}
        handle_krslast_command("/krslast", replies.append, ctx)
        assert "ikke aktivert" in replies[0]

    def test_default_returns_last_10(self, conn):
        store_n(conn, 20)
        replies = collect_replies(conn, "/krslast")
        combined = "\n".join(replies)
        # Should contain messages 10-19, not 0-9
        for i in range(10, 20):
            assert f"Message {i}" in combined
        for i in range(10):
            assert f"Message {i}\n" not in combined and not combined.endswith(f"Message {i}")

    def test_custom_count(self, conn):
        store_n(conn, 15)
        replies = collect_replies(conn, "/krslast 5")
        combined = "\n".join(replies)
        for i in range(10, 15):
            assert f"Message {i}" in combined
        for i in range(10):
            assert f"Message {i}\n" not in combined and not combined.endswith(f"Message {i}")

    def test_returns_in_chronological_order(self, conn):
        store_n(conn, 5)
        replies = collect_replies(conn, "/krslast 5")
        combined = "\n".join(replies)
        positions = [combined.index(f"Message {i}") for i in range(5)]
        assert positions == sorted(positions)

    def test_fewer_messages_than_requested(self, conn):
        store_n(conn, 3)
        replies = collect_replies(conn, "/krslast 10")
        combined = "\n".join(replies)
        for i in range(3):
            assert f"Message {i}" in combined

    def test_over_limit_is_clamped(self, conn):
        store_n(conn, 5)
        over = MAX_KRSLAST + 50
        replies = collect_replies(conn, f"/krslast {over}")
        assert str(MAX_KRSLAST) in replies[0]

    def test_invalid_arg_returns_error(self, conn):
        replies = collect_replies(conn, "/krslast abc")
        assert "Bruk:" in replies[0]

    def test_zero_arg_returns_error(self, conn):
        replies = collect_replies(conn, "/krslast 0")
        assert "Bruk:" in replies[0]

    def test_all_pages_within_byte_limit(self, conn):
        store_n(conn, 30)
        for msg in collect_replies(conn, "/krslast 30"):
            assert len(msg.encode("utf-8")) <= MAX_BYTES

    def test_single_message_no_counter(self, conn):
        store_n(conn, 1)
        replies = collect_replies(conn, "/krslast")
        assert len(replies) == 1
        assert not replies[0].startswith("[")

    def test_multi_page_has_counter(self, conn):
        store_n(conn, 20)
        replies = collect_replies(conn, "/krslast 20")
        if len(replies) > 1:
            assert replies[0].startswith("[1/")
