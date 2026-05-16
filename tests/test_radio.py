"""
Tests for radio.py — format_radio_messages byte safety and pagination.
"""

import pytest
from radio import format_radio_messages
from constants import MAX_BYTES


def make_radio_data(n_hf_bands=10, include_vhf=True):
    hf_bands = {
        f"{b}m": {"day": "Good", "night": "Fair"}
        for b in [160, 80, 60, 40, 30, 20, 17, 15, 12, 10][:n_hf_bands]
    }
    vhf = [("Aurora", "Active"), ("E-skip EU", "Good")] if include_vhf else []
    return {
        "sfi": "142",
        "kindex": "2",
        "aindex": "8",
        "geomagfield": "Quiet",
        "signalnoise": "S1-S2",
        "updated": "14 May 2026 1200 UTC",
        "hf_bands": hf_bands,
        "vhf": vhf,
    }


class TestFormatRadioMessages:
    def test_byte_safe(self):
        data = make_radio_data()
        for msg in format_radio_messages(data):
            assert len(msg.encode("utf-8")) <= MAX_BYTES, \
                f"Message exceeds {MAX_BYTES} bytes:\n{msg!r}"

    def test_returns_at_least_one_message(self):
        assert len(format_radio_messages(make_radio_data())) >= 1

    def test_single_page_no_counter_when_small(self):
        data = make_radio_data(n_hf_bands=2, include_vhf=False)
        messages = format_radio_messages(data)
        if len(messages) == 1:
            assert not messages[0].startswith("[")

    def test_multi_page_counter(self):
        data = make_radio_data(n_hf_bands=10, include_vhf=True)
        messages = format_radio_messages(data)
        if len(messages) > 1:
            assert messages[0].startswith("[1/")
            assert messages[-1].startswith(f"[{len(messages)}/")

    def test_no_vhf_section_when_empty(self):
        data = make_radio_data(include_vhf=False)
        combined = "\n".join(format_radio_messages(data))
        assert "VHF" not in combined

    def test_contains_sfi(self):
        data = make_radio_data()
        combined = "\n".join(format_radio_messages(data))
        assert "SFI:142" in combined
