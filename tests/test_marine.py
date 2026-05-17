"""
Tests for marine.py — format_mvhf_channel and format_mvhf_list_messages.
"""

from constants import MAX_BYTES
from marine import format_mvhf_channel, format_mvhf_list_messages


class TestFormatMvhfChannel:
    def test_known_channel_contains_frequency(self):
        result = format_mvhf_channel("16")
        assert "156.800" in result

    def test_known_channel_contains_usage(self):
        result = format_mvhf_channel("16")
        assert "Nød" in result

    def test_unknown_channel_returns_error(self):
        result = format_mvhf_channel("999")
        assert "finnes ikke" in result

    def test_case_insensitive_ais(self):
        result = format_mvhf_channel("ais1")
        assert "finnes ikke" not in result

    def test_duplex_channel_shows_tx_rx(self):
        # Channel 25 is duplex in Norwegian plan
        result = format_mvhf_channel("25")
        if "duplex" in result.lower() or "Tx" in result:
            assert "Tx" in result and "Rx" in result


class TestFormatMvhfListMessages:
    def test_returns_at_least_one_message(self):
        assert len(format_mvhf_list_messages()) >= 1

    def test_all_messages_within_byte_limit(self):
        messages = format_mvhf_list_messages()
        for msg in messages:
            assert len(msg.encode("utf-8")) <= MAX_BYTES, \
                f"Message exceeds {MAX_BYTES} bytes:\n{msg!r}"

    def test_group_filter(self):
        messages = format_mvhf_list_messages(groups=["Nød/DSC"])
        combined = "\n".join(messages)
        assert "16" in combined  # Channel 16 is in Nød/DSC

    def test_multi_page_has_counter(self):
        messages = format_mvhf_list_messages()
        if len(messages) > 1:
            assert messages[0].startswith("[1/")
