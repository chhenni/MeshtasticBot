"""
Tests for per-sender rate limiting in make_receive_handler.
"""

import itertools
import time
from unittest.mock import MagicMock, patch

from main import make_receive_handler

_pkt_counter = itertools.count(1)


def make_packet(text: str, sender: str = "!abc", channel: int = 1) -> dict:
    return {
        "decoded": {"text": text},
        "fromId": sender,
        "toId": "^all",
        "channel": channel,
        "id": next(_pkt_counter),  # unique per call so dedup doesn't interfere
    }


def make_handler(bucket_size: float = 5.0, refill_rate: float = 0.0):
    iface = MagicMock()
    iface.nodes = {}
    return make_receive_handler(iface, channel=1, bucket_size=bucket_size, refill_rate=refill_rate), iface


class TestRateLimit:
    def _dispatch(self, handler, packet, mock_cmd):
        """Patch COMMANDS so /ping routes to mock_cmd, then dispatch packet."""
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(packet)

    def test_first_command_goes_through(self):
        handler, _ = make_handler()
        mock_cmd = MagicMock()
        self._dispatch(handler, make_packet("/ping"), mock_cmd)
        assert mock_cmd.call_count == 1

    def test_second_command_within_cooldown_blocked(self):
        handler, _ = make_handler(bucket_size=1, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(make_packet("/ping"))
                handler(make_packet("/ping"))
        assert mock_cmd.call_count == 1

    def test_command_after_refill_goes_through(self):
        handler, _ = make_handler(bucket_size=1, refill_rate=5.0)  # fast refill
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(make_packet("/ping"))
                time.sleep(0.3)  # 0.3s * 5 tok/s = 1.5 tokens refilled
                handler(make_packet("/ping"))
        assert mock_cmd.call_count == 2

    def test_different_senders_are_independent(self):
        handler, _ = make_handler(bucket_size=1, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(make_packet("/ping", sender="!aaa"))
                handler(make_packet("/ping", sender="!bbb"))
        assert mock_cmd.call_count == 2

    def test_non_command_messages_bypass_rate_limiting(self):
        handler, _ = make_handler(bucket_size=1, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(make_packet("hello world"))
                handler(make_packet("hello world"))
        assert mock_cmd.call_count == 0

    def test_large_bucket_allows_all(self):
        handler, _ = make_handler(bucket_size=100, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(make_packet("/ping"))
                handler(make_packet("/ping"))
        assert mock_cmd.call_count == 2


class TestPacketDeduplication:
    """Same packet ID must not trigger a command more than once."""

    def _dispatch(self, handler, packet, mock_cmd):
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(packet)

    def test_duplicate_packet_id_ignored(self):
        handler, _ = make_handler(bucket_size=100, refill_rate=0)
        mock_cmd = MagicMock()
        pkt = make_packet("/ping", sender="!abc")
        pkt["id"] = "pkt-dupe-1"
        # Simulate same packet delivered twice (relayed by two nodes)
        self._dispatch(handler, pkt, mock_cmd)
        self._dispatch(handler, pkt, mock_cmd)
        assert mock_cmd.call_count == 1

    def test_different_packet_ids_both_processed(self):
        handler, _ = make_handler(bucket_size=100, refill_rate=0)
        mock_cmd = MagicMock()
        pkt1 = {**make_packet("/ping"), "id": "pkt-A"}
        pkt2 = {**make_packet("/ping"), "id": "pkt-B"}
        self._dispatch(handler, pkt1, mock_cmd)
        self._dispatch(handler, pkt2, mock_cmd)
        assert mock_cmd.call_count == 2

    def test_packet_without_id_always_processed(self):
        handler, _ = make_handler(bucket_size=100, refill_rate=0)
        mock_cmd = MagicMock()
        pkt = make_packet("/ping")
        del pkt["id"]
        self._dispatch(handler, pkt, mock_cmd)
        self._dispatch(handler, pkt, mock_cmd)
        assert mock_cmd.call_count == 2
