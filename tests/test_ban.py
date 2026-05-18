"""
Tests for the ban system — DB layer and integration with make_receive_handler.
"""

from unittest.mock import MagicMock, patch

import pytest

from db import ban_node, get_banned_nodes, init_db, is_banned, unban_node
from main import make_receive_handler


@pytest.fixture
def conn():
    return init_db(":memory:")


class TestBanDB:
    def test_node_not_banned_by_default(self, conn):
        assert is_banned(conn, "!abc") is False

    def test_ban_node(self, conn):
        ban_node(conn, "!abc")
        assert is_banned(conn, "!abc") is True

    def test_unban_node(self, conn):
        ban_node(conn, "!abc")
        unban_node(conn, "!abc")
        assert is_banned(conn, "!abc") is False

    def test_ban_with_reason(self, conn):
        ban_node(conn, "!abc", reason="Spamming")
        rows = get_banned_nodes(conn)
        assert rows[0]["reason"] == "Spamming"

    def test_ban_without_reason(self, conn):
        ban_node(conn, "!abc")
        rows = get_banned_nodes(conn)
        assert rows[0]["reason"] is None

    def test_get_banned_nodes_empty(self, conn):
        assert get_banned_nodes(conn) == []

    def test_get_banned_nodes_returns_all_banned(self, conn):
        ban_node(conn, "!abc")
        ban_node(conn, "!xyz")
        rows = get_banned_nodes(conn)
        ids = [r["node_id"] for r in rows]
        assert "!abc" in ids
        assert "!xyz" in ids

    def test_banning_already_banned_node_is_idempotent(self, conn):
        ban_node(conn, "!abc")
        ban_node(conn, "!abc")  # should not raise
        assert len(get_banned_nodes(conn)) == 1

    def test_unbanning_non_banned_node_is_idempotent(self, conn):
        unban_node(conn, "!abc")  # should not raise
        assert is_banned(conn, "!abc") is False


class TestBanIntegration:
    """Banned nodes are silently ignored in make_receive_handler."""

    def make_packet(self, text="/ ping", sender="!bad"):
        return {"decoded": {"text": text}, "fromId": sender, "toId": "^all", "channel": 1, "id": "p1"}

    def test_banned_node_command_is_ignored(self, conn):
        ban_node(conn, "!bad")
        iface = MagicMock()
        iface.nodes = {}
        handler = make_receive_handler(iface, channel=1, db_conn=conn)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(self.make_packet("/ping", sender="!bad"))
        assert mock_cmd.call_count == 0

    def test_banned_node_gets_no_reply(self, conn):
        ban_node(conn, "!bad")
        iface = MagicMock()
        iface.nodes = {}
        handler = make_receive_handler(iface, channel=1, db_conn=conn)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(self.make_packet("/ping", sender="!bad"))
        assert iface.sendText.call_count == 0

    def test_non_banned_node_command_goes_through(self, conn):
        iface = MagicMock()
        iface.nodes = {}
        handler = make_receive_handler(iface, channel=1, db_conn=conn)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(self.make_packet("/ping", sender="!good"))
        assert mock_cmd.call_count == 1

    def test_banned_node_attempt_logged_as_banned(self, conn):
        from db import get_command_log
        ban_node(conn, "!bad")
        iface = MagicMock()
        iface.nodes = {}
        handler = make_receive_handler(iface, channel=1, db_conn=conn)
        with patch("main.COMMANDS", {"/ping": MagicMock()}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(self.make_packet("/ping", sender="!bad"))
        rows = get_command_log(conn, node_id="!bad")
        assert len(rows) == 1
        assert rows[0]["status"] == "banned"

    def test_successful_command_logged_as_ok(self, conn):
        from db import get_command_log

        def ping(text, reply_fn, ctx):
            reply_fn("pong")

        iface = MagicMock()
        iface.nodes = {}
        handler = make_receive_handler(iface, channel=1, db_conn=conn)
        with patch("main.COMMANDS", {"/ping": ping}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(self.make_packet("/ping", sender="!good"))
        rows = get_command_log(conn, node_id="!good")
        assert len(rows) == 1
        assert rows[0]["status"] == "ok"

    def test_rate_limited_command_logged_as_rate_limited(self, conn):
        from db import get_command_log
        iface = MagicMock()
        iface.nodes = {}
        handler = make_receive_handler(iface, channel=1, db_conn=conn, bucket_size=1, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(self.make_packet("/ping", sender="!abc"))  # ok
                handler(self.make_packet("/ping", sender="!abc"))  # rate_limited
        rows = get_command_log(conn, node_id="!abc")
        statuses = [r["status"] for r in rows]
        assert "ok" in statuses
        assert "rate_limited" in statuses
