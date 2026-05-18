"""
Tests for token bucket rate limiting in make_receive_handler.

The token bucket replaces the simple cooldown with a cost-based system:
- Each sender has a bucket of tokens (default capacity: 5)
- Tokens refill at a configurable rate (default: 1 per 10s)
- Each command costs tokens based on how many messages it may generate:
    1 token: /ping, /help, /whois
    2 tokens: /nodes, /radio, /alert, /calling, /mvhf
    3 tokens: /weather, /24hour, /bandplan, /bandplan_check, /krslog, /krslast
- Commands that exceed the available tokens are silently dropped
"""

import time
from unittest.mock import MagicMock, patch

from main import COMMAND_COSTS, make_receive_handler


def make_packet(text: str, sender: str = "!abc", channel: int = 1) -> dict:
    return {
        "decoded": {"text": text},
        "fromId": sender,
        "toId": "^all",
        "channel": channel,
        "id": "pkt-tb",
    }


def make_handler(bucket_size: int = 5, refill_rate: float = 1.0):
    """Create a handler with token bucket rate limiting.

    refill_rate: tokens per second (default 1/10s → 0.1, but use 1.0 in tests for speed).
    """
    iface = MagicMock()
    iface.nodes = {}
    return make_receive_handler(iface, channel=1, bucket_size=bucket_size, refill_rate=refill_rate), iface


class TestCommandCosts:
    def test_ping_costs_one_token(self):
        assert COMMAND_COSTS["/ping"] == 1

    def test_help_costs_one_token(self):
        assert COMMAND_COSTS["/help"] == 1

    def test_whois_costs_one_token(self):
        assert COMMAND_COSTS["/whois"] == 1

    def test_nodes_costs_two_tokens(self):
        assert COMMAND_COSTS["/nodes"] == 2

    def test_radio_costs_two_tokens(self):
        assert COMMAND_COSTS["/radio"] == 2

    def test_alert_costs_two_tokens(self):
        assert COMMAND_COSTS["/alert"] == 2

    def test_weather_costs_three_tokens(self):
        assert COMMAND_COSTS["/weather"] == 3

    def test_krslog_costs_three_tokens(self):
        assert COMMAND_COSTS["/krslog"] == 3

    def test_bandplan_costs_three_tokens(self):
        assert COMMAND_COSTS["/bandplan"] == 3

    def test_all_commands_have_a_cost(self):
        from main import COMMANDS
        for cmd in COMMANDS:
            assert cmd in COMMAND_COSTS, f"{cmd} missing from COMMAND_COSTS"


class TestTokenBucket:
    def _dispatch(self, handler, packet, mock_cmd, cmd="/ping"):
        with patch("main.COMMANDS", {cmd: mock_cmd}):
            with patch("main.COMMAND_COSTS", {cmd: COMMAND_COSTS.get(cmd, 1)}):
                handler(packet)

    def test_first_command_goes_through(self):
        handler, _ = make_handler()
        mock_cmd = MagicMock()
        self._dispatch(handler, make_packet("/ping"), mock_cmd)
        assert mock_cmd.call_count == 1

    def test_bucket_allows_burst_within_capacity(self):
        """5-token bucket with 1-token commands: 5 commands go through."""
        handler, _ = make_handler(bucket_size=5, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                for _ in range(5):
                    handler(make_packet("/ping"))
        assert mock_cmd.call_count == 5

    def test_bucket_blocks_when_empty(self):
        """After 5 one-token commands, the 6th is blocked."""
        handler, _ = make_handler(bucket_size=5, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                for _ in range(6):
                    handler(make_packet("/ping"))
        assert mock_cmd.call_count == 5

    def test_expensive_command_costs_more_tokens(self):
        """3-token /weather from a 5-token bucket leaves 2 tokens → only 2 more /ping."""
        handler, _ = make_handler(bucket_size=5, refill_rate=0)
        weather_mock = MagicMock()
        ping_mock = MagicMock()
        with patch("main.COMMANDS", {"/weather": weather_mock, "/ping": ping_mock}):
            with patch("main.COMMAND_COSTS", {"/weather": 3, "/ping": 1}):
                handler(make_packet("/weather"))   # costs 3 → 2 left
                handler(make_packet("/ping"))       # costs 1 → 1 left
                handler(make_packet("/ping"))       # costs 1 → 0 left
                handler(make_packet("/ping"))       # blocked — no tokens
        assert weather_mock.call_count == 1
        assert ping_mock.call_count == 2

    def test_tokens_refill_over_time(self):
        """Tokens refill at refill_rate per second; blocked command works after refill."""
        handler, _ = make_handler(bucket_size=1, refill_rate=5.0)  # fast refill for test
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(make_packet("/ping"))   # uses last token
                handler(make_packet("/ping"))   # blocked
                time.sleep(0.3)                 # 0.3s * 5 tok/s = 1.5 tokens refilled
                handler(make_packet("/ping"))   # should go through
        assert mock_cmd.call_count == 2

    def test_different_senders_have_independent_buckets(self):
        handler, _ = make_handler(bucket_size=1, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(make_packet("/ping", sender="!aaa"))  # uses !aaa's token
                handler(make_packet("/ping", sender="!bbb"))  # !bbb still has token
        assert mock_cmd.call_count == 2

    def test_non_command_bypasses_bucket(self):
        handler, _ = make_handler(bucket_size=1, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/ping": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/ping": 1}):
                handler(make_packet("hello"))
                handler(make_packet("hello"))
        assert mock_cmd.call_count == 0

    def test_command_too_expensive_for_current_tokens_is_blocked(self):
        """If bucket has 2 tokens but command costs 3, it's blocked."""
        handler, _ = make_handler(bucket_size=2, refill_rate=0)
        mock_cmd = MagicMock()
        with patch("main.COMMANDS", {"/weather": mock_cmd}):
            with patch("main.COMMAND_COSTS", {"/weather": 3}):
                handler(make_packet("/weather"))
        assert mock_cmd.call_count == 0
