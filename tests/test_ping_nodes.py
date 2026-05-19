"""
Tests for handle_ping_command and handle_nodes_command.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from commands import handle_nodes_command, handle_ping_command
from constants import MAX_BYTES


def make_interface(nodes: dict) -> MagicMock:
    iface = MagicMock()
    iface.nodes = nodes
    return iface


def ctx(nodes: dict, start_time=None) -> dict:
    return {
        "interface": make_interface(nodes),
        "sender": "!abc",
        "db_conn": None,
        "log_channel": None,
        "start_time": start_time,
        "county": None,
    }


# ---------------------------------------------------------------------------
# /ping
# ---------------------------------------------------------------------------

class TestPingCommand:
    def test_reply_starts_with_pong(self):
        replies = []
        handle_ping_command("/ping", replies.append, ctx({}))
        assert "Pong" in replies[0]

    def test_node_count_zero(self):
        replies = []
        handle_ping_command("/ping", replies.append, ctx({}))
        assert "0" in replies[0]

    def test_node_count_nonzero(self):
        replies = []
        handle_ping_command("/ping", replies.append, ctx({"!a": {}, "!b": {}}))
        assert "2" in replies[0]

    def test_uptime_minutes_only(self):
        start = datetime.now(timezone.utc) - timedelta(minutes=5)
        replies = []
        handle_ping_command("/ping", replies.append, ctx({}, start_time=start))
        assert "5m" in replies[0]

    def test_uptime_hours_and_minutes(self):
        start = datetime.now(timezone.utc) - timedelta(hours=2, minutes=30)
        replies = []
        handle_ping_command("/ping", replies.append, ctx({}, start_time=start))
        assert "2t" in replies[0]
        assert "30m" in replies[0]

    def test_unknown_uptime_when_no_start_time(self):
        replies = []
        handle_ping_command("/ping", replies.append, ctx({}))
        assert "ukjent" in replies[0]

    def test_single_reply(self):
        replies = []
        handle_ping_command("/ping", replies.append, ctx({}))
        assert len(replies) == 1


# ---------------------------------------------------------------------------
# /nodes
# ---------------------------------------------------------------------------

class TestNodesCommand:
    def test_empty_nodes(self):
        replies = []
        handle_nodes_command("/nodes", replies.append, ctx({}))
        assert len(replies) == 1
        assert "Ingen" in replies[0]

    def test_single_node_with_snr(self):
        replies = []
        nodes = {"!abc": {"user": {"longName": "My Node"}, "snr": 7.5}}
        handle_nodes_command("/nodes", replies.append, ctx(nodes))
        combined = "\n".join(replies)
        assert "My Node" in combined
        assert "7.5" in combined

    def test_node_without_snr(self):
        replies = []
        nodes = {"!abc": {"user": {"longName": "No SNR Node"}}}
        handle_nodes_command("/nodes", replies.append, ctx(nodes))
        assert "No SNR Node" in "\n".join(replies)

    def test_node_falls_back_to_short_name(self):
        replies = []
        nodes = {"!abc": {"user": {"shortName": "SN"}}}
        handle_nodes_command("/nodes", replies.append, ctx(nodes))
        assert "SN" in "\n".join(replies)

    def test_node_falls_back_to_id(self):
        replies = []
        nodes = {"!abc": {}}
        handle_nodes_command("/nodes", replies.append, ctx(nodes))
        assert "!abc" in "\n".join(replies)

    def test_header_includes_count(self):
        replies = []
        nodes = {"!a": {"user": {"longName": "A"}}, "!b": {"user": {"longName": "B"}}}
        handle_nodes_command("/nodes", replies.append, ctx(nodes))
        assert "2" in replies[0]

    def test_all_replies_within_max_bytes(self):
        replies = []
        nodes = {f"!node{i}": {"user": {"longName": f"Long Name Node {i}"}, "snr": float(i)}
                 for i in range(20)}
        handle_nodes_command("/nodes", replies.append, ctx(nodes))
        for r in replies:
            assert len(r.encode("utf-8")) <= MAX_BYTES


class TestHelpMessageSizes:
    """Regression test: all help pages must fit within MAX_BYTES."""

    def test_all_help_pages_fit_in_max_bytes(self):
        from commands import build_help_pages
        from constants import MAX_BYTES

        # Check both unprivileged and privileged views
        for privileged in (False, True):
            pages = build_help_pages(privileged=privileged)
            oversized = [
                (i + 1, len(page.encode("utf-8")))
                for i, page in enumerate(pages)
                if len(page.encode("utf-8")) > MAX_BYTES
            ]
            assert oversized == [], (
                f"Help page(s) (privileged={privileged}) exceed {MAX_BYTES} bytes: "
                + ", ".join(f"page {i}={size}B" for i, size in oversized)
            )
