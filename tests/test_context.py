"""
Tests for BotContext TypedDict (issue #8).

Verifies that BotContext has the expected keys and types, and that
handlers accept BotContext where they previously accepted plain dict.
"""

from datetime import datetime, timezone
from typing import get_type_hints

from context import BotContext


class TestBotContextStructure:
    def test_is_importable(self):
        from context import BotContext  # noqa: F401

    def test_has_interface_key(self):
        hints = get_type_hints(BotContext)
        assert "interface" in hints

    def test_has_sender_key(self):
        hints = get_type_hints(BotContext)
        assert "sender" in hints

    def test_has_db_conn_key(self):
        hints = get_type_hints(BotContext)
        assert "db_conn" in hints

    def test_has_log_channel_key(self):
        hints = get_type_hints(BotContext)
        assert "log_channel" in hints

    def test_has_start_time_key(self):
        hints = get_type_hints(BotContext)
        assert "start_time" in hints

    def test_has_county_key(self):
        hints = get_type_hints(BotContext)
        assert "county" in hints

    def test_can_construct_valid_instance(self):
        ctx: BotContext = {
            "interface": None,
            "sender": "!aabbccdd",
            "db_conn": None,
            "log_channel": None,
            "start_time": None,
            "county": None,
        }
        assert ctx["sender"] == "!aabbccdd"

    def test_sender_is_str(self):
        hints = get_type_hints(BotContext)
        assert hints["sender"] is str


class TestHandlersAcceptBotContext:
    """Smoke-test that key handlers still work when passed a BotContext."""

    def _ctx(self, **overrides) -> BotContext:
        base: BotContext = {
            "interface": None,
            "sender": "!aabbccdd",
            "db_conn": None,
            "log_channel": None,
            "start_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "county": None,
        }
        base.update(overrides)
        return base

    def test_ping_handler_accepts_bot_context(self):
        from unittest.mock import MagicMock

        from commands import COMMANDS
        mock_interface = MagicMock()
        mock_interface.nodes = {}
        replies = []
        COMMANDS["/ping"]("", replies.append, self._ctx(interface=mock_interface))
        assert any("pong" in r.lower() for r in replies)

    def test_krslog_handler_accepts_bot_context_with_db(self):
        from commands import COMMANDS
        from db import init_db
        conn = init_db(":memory:")
        replies = []
        COMMANDS["/krslog"]("/krslog", replies.append, self._ctx(db_conn=conn))
        assert len(replies) >= 1
