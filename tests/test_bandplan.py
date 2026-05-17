"""
Tests for bandplan.py — resolve_band, parse_frequency_mhz, lookup_frequency,
and the message formatting functions.
"""

import pytest

from bandplan import (
    BANDPLAN,
    CALLING_FREQUENCIES,
    format_bandplan_messages,
    format_calling_messages,
    lookup_frequency,
    parse_frequency_mhz,
    resolve_band,
)
from constants import MAX_BYTES

# ---------------------------------------------------------------------------
# resolve_band
# ---------------------------------------------------------------------------

class TestResolveBand:
    def test_canonical_key_passthrough(self):
        assert resolve_band("20m") == "20m"

    def test_alias_without_suffix(self):
        assert resolve_band("20") == "20m"

    def test_alias_case_insensitive(self):
        assert resolve_band("40M") == "40m"

    def test_alias_whitespace(self):
        assert resolve_band("  2m  ") == "2m"

    def test_unknown_returns_none(self):
        assert resolve_band("99m") is None

    def test_all_bands_resolve(self):
        for band in BANDPLAN:
            assert resolve_band(band) == band


# ---------------------------------------------------------------------------
# parse_frequency_mhz
# ---------------------------------------------------------------------------

class TestParseFrequencyMhz:
    def test_plain_mhz(self):
        assert parse_frequency_mhz("14.225") == pytest.approx(14.225)

    def test_explicit_mhz_suffix(self):
        assert parse_frequency_mhz("14.225 MHz") == pytest.approx(14.225)

    def test_khz_suffix(self):
        assert parse_frequency_mhz("14225 kHz") == pytest.approx(14.225)

    def test_large_bare_number_treated_as_khz(self):
        assert parse_frequency_mhz("144300") == pytest.approx(144.3)

    def test_small_bare_number_treated_as_mhz(self):
        assert parse_frequency_mhz("14.1") == pytest.approx(14.1)

    def test_comma_decimal_separator(self):
        assert parse_frequency_mhz("14,225") == pytest.approx(14.225)

    def test_invalid_returns_none(self):
        assert parse_frequency_mhz("not a frequency") is None

    def test_empty_returns_none(self):
        assert parse_frequency_mhz("") is None


# ---------------------------------------------------------------------------
# lookup_frequency
# ---------------------------------------------------------------------------

class TestLookupFrequency:
    def test_in_band_returns_result(self):
        result = lookup_frequency(14.225)
        assert result is not None
        band, freq_range, mode = result
        assert band == "20m"

    def test_out_of_band_returns_none(self):
        assert lookup_frequency(15.0) is None

    def test_band_edge_low(self):
        # 14.000 MHz is the lower edge of 20m
        result = lookup_frequency(14.0)
        assert result is not None
        assert result[0] == "20m"

    def test_vhf_frequency(self):
        result = lookup_frequency(144.3)
        assert result is not None
        assert result[0] == "2m"

    def test_below_all_bands(self):
        assert lookup_frequency(0.5) is None


# ---------------------------------------------------------------------------
# format_bandplan_messages — byte safety and pagination
# ---------------------------------------------------------------------------

class TestFormatBandplanMessages:
    @pytest.mark.parametrize("band", list(BANDPLAN.keys()))
    def test_all_messages_within_byte_limit(self, band):
        messages = format_bandplan_messages(band)
        for msg in messages:
            assert len(msg.encode("utf-8")) <= MAX_BYTES, \
                f"{band}: message exceeds {MAX_BYTES} bytes:\n{msg!r}"

    @pytest.mark.parametrize("band", list(BANDPLAN.keys()))
    def test_returns_at_least_one_message(self, band):
        assert len(format_bandplan_messages(band)) >= 1

    def test_single_page_has_no_counter(self):
        # Find a band with few segments (e.g. 60m)
        messages = format_bandplan_messages("60m")
        if len(messages) == 1:
            assert not messages[0].startswith("[")

    def test_multi_page_has_counter(self):
        # 80m has many segments and should produce multiple pages
        messages = format_bandplan_messages("80m")
        if len(messages) > 1:
            assert messages[0].startswith("[1/")
            assert messages[-1].startswith(f"[{len(messages)}/")


# ---------------------------------------------------------------------------
# format_calling_messages — byte safety
# ---------------------------------------------------------------------------

class TestFormatCallingMessages:
    @pytest.mark.parametrize("band", list(CALLING_FREQUENCIES.keys()))
    def test_all_messages_within_byte_limit(self, band):
        messages = format_calling_messages(band)
        for msg in messages:
            assert len(msg.encode("utf-8")) <= MAX_BYTES
