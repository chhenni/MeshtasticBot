"""
Tests for per-sender rate limiting in make_receive_handler.
"""

import time
from unittest.mock import MagicMock, patch

from main import make_receive_handler


def make_packet(text: str, sender: str = "!abc", channel: int = 1) -> dict:
    return {
        "decoded": {"text": text},
        "fromId": sender,
        "toId": "^all",
        "channel": channel,
        "id": "pkt-1",
    }


def make_handler(rate_limit_seconds: int = 10):
    iface = MagicMock()
    iface.nodes = {}
    return make_receive_handler(iface, channel=1, rate_limit_seconds=rate_limit_seconds), iface


class TestRateLimit:
    def _dispatch(self, handler, packet, mock_cmd):
        """Patch COMMANDS so /ping routes to mock_cmd, then dispatch packet."""
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            handler(packet)

    def test_first_command_goes_through(self):
        handler, _ = make_handler()
        mock_cmd = MagicMock()
        self._dispatch(handler, make_packet("/ping"), mock_cmd)
        assert mock_cmd.call_count == 1

    def test_second_command_within_cooldown_blocked(self):
        handler, _ = make_handler(rate_limit_seconds=10)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            handler(make_packet("/ping"))
            handler(make_packet("/ping"))
        assert mock_cmd.call_count == 1

    def test_command_after_cooldown_goes_through(self):
        handler, _ = make_handler(rate_limit_seconds=1)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            handler(make_packet("/ping"))
            time.sleep(1.1)
            handler(make_packet("/ping"))
        assert mock_cmd.call_count == 2

    def test_different_senders_are_independent(self):
        handler, _ = make_handler(rate_limit_seconds=10)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            handler(make_packet("/ping", sender="!aaa"))
            handler(make_packet("/ping", sender="!bbb"))
        assert mock_cmd.call_count == 2

    def test_non_command_messages_bypass_rate_limiting(self):
        """Messages that aren't in COMMANDS are never dispatched."""
        handler, _ = make_handler(rate_limit_seconds=10)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            handler(make_packet("hello world"))
            handler(make_packet("hello world"))
        assert mock_cmd.call_count == 0

    def test_zero_rate_limit_allows_all(self):
        handler, _ = make_handler(rate_limit_seconds=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            handler(make_packet("/ping"))
            handler(make_packet("/ping"))
        assert mock_cmd.call_count == 2
