"""
Tests for validate_config() in main.py.
"""

import pytest

from main import validate_config

VALID = {
    "connection": {"type": "serial"},
    "weather": {"enabled": True, "county": "42"},
}


class TestValidateConfig:
    def test_valid_config_passes(self):
        validate_config(VALID)  # should not raise

    def test_valid_tcp_with_host(self):
        cfg = {"connection": {"type": "tcp", "host": "192.168.1.1"}, "weather": {"county": "42"}}
        validate_config(cfg)

    def test_valid_ble(self):
        cfg = {"connection": {"type": "ble"}, "weather": {"county": "42"}}
        validate_config(cfg)

    def test_invalid_connection_type(self):
        cfg = {**VALID, "connection": {"type": "usb"}}
        with pytest.raises(ValueError, match="connection.type"):
            validate_config(cfg)

    def test_tcp_without_host_raises(self):
        cfg = {"connection": {"type": "tcp"}, "weather": {"county": "42"}}
        with pytest.raises(ValueError, match="connection.host"):
            validate_config(cfg)

    def test_weather_enabled_without_county_raises(self):
        cfg = {"connection": {"type": "serial"}, "weather": {"enabled": True, "county": ""}}
        with pytest.raises(ValueError, match="weather.county"):
            validate_config(cfg)

    def test_weather_disabled_without_county_passes(self):
        cfg = {"connection": {"type": "serial"}, "weather": {"enabled": False}}
        validate_config(cfg)  # should not raise

    def test_weather_defaults_to_enabled(self):
        """Omitting weather.enabled defaults to True, so county is required."""
        cfg = {"connection": {"type": "serial"}, "weather": {}}
        with pytest.raises(ValueError, match="weather.county"):
            validate_config(cfg)

    def test_multiple_errors_reported_together(self):
        cfg = {"connection": {"type": "tcp"}, "weather": {"enabled": True, "county": ""}}
        with pytest.raises(ValueError) as exc_info:
            validate_config(cfg)
        msg = str(exc_info.value)
        assert "connection.host" in msg
        assert "weather.county" in msg

    def test_missing_connection_section_defaults_to_serial(self):
        cfg = {"weather": {"county": "42"}}
        validate_config(cfg)  # serial is the default, no error


class TestValidateConfigNewChecks:
    """Tests for additional validation from issue #4."""

    BASE = {
        "connection": {"type": "serial"},
        "weather": {"enabled": True, "county": "42"},
    }

    def _cfg(self, **overrides):
        import copy
        c = copy.deepcopy(self.BASE)
        for key, val in overrides.items():
            parts = key.split(".")
            d = c
            for p in parts[:-1]:
                d = d.setdefault(p, {})
            d[parts[-1]] = val
        return c

    # retain_days
    def test_retain_days_zero_raises(self):
        with pytest.raises(ValueError, match="retain_days"):
            validate_config(self._cfg(**{"message_log.retain_days": 0}))

    def test_retain_days_negative_raises(self):
        with pytest.raises(ValueError, match="retain_days"):
            validate_config(self._cfg(**{"message_log.retain_days": -5}))

    def test_retain_days_positive_passes(self):
        validate_config(self._cfg(**{"message_log.retain_days": 30}))

    def test_retain_days_missing_passes(self):
        validate_config(self.BASE)  # default applied in main(), not required here

    # web.port
    def test_web_port_zero_raises(self):
        with pytest.raises(ValueError, match="web.port"):
            validate_config(self._cfg(**{"web.port": 0}))

    def test_web_port_too_high_raises(self):
        with pytest.raises(ValueError, match="web.port"):
            validate_config(self._cfg(**{"web.port": 65536}))

    def test_web_port_valid_passes(self):
        validate_config(self._cfg(**{"web.port": 8080}))

    def test_web_port_boundary_low(self):
        validate_config(self._cfg(**{"web.port": 1}))

    def test_web_port_boundary_high(self):
        validate_config(self._cfg(**{"web.port": 65535}))

    def test_web_port_missing_passes(self):
        validate_config(self.BASE)

    # weather.county format (2-digit Norwegian fylkesnummer)
    def test_county_single_digit_raises(self):
        with pytest.raises(ValueError, match="weather.county"):
            validate_config(self._cfg(**{"weather.county": "3"}))

    def test_county_three_digits_raises(self):
        with pytest.raises(ValueError, match="weather.county"):
            validate_config(self._cfg(**{"weather.county": "123"}))

    def test_county_non_numeric_raises(self):
        with pytest.raises(ValueError, match="weather.county"):
            validate_config(self._cfg(**{"weather.county": "AB"}))

    def test_county_two_digits_passes(self):
        validate_config(self._cfg(**{"weather.county": "03"}))

    def test_county_integer_two_digits_passes(self):
        validate_config(self._cfg(**{"weather.county": 42}))

    # rate_limit.bucket_size
    def test_bucket_size_zero_raises(self):
        with pytest.raises(ValueError, match="bucket_size"):
            validate_config(self._cfg(**{"rate_limit.bucket_size": 0}))

    def test_bucket_size_negative_raises(self):
        with pytest.raises(ValueError, match="bucket_size"):
            validate_config(self._cfg(**{"rate_limit.bucket_size": -1}))

    def test_bucket_size_positive_passes(self):
        validate_config(self._cfg(**{"rate_limit.bucket_size": 5}))

    def test_bucket_size_missing_passes(self):
        validate_config(self.BASE)

    # rate_limit.refill_rate
    def test_refill_rate_zero_raises(self):
        with pytest.raises(ValueError, match="refill_rate"):
            validate_config(self._cfg(**{"rate_limit.refill_rate": 0}))

    def test_refill_rate_negative_raises(self):
        with pytest.raises(ValueError, match="refill_rate"):
            validate_config(self._cfg(**{"rate_limit.refill_rate": -0.1}))

    def test_refill_rate_positive_passes(self):
        validate_config(self._cfg(**{"rate_limit.refill_rate": 0.1}))

    def test_refill_rate_missing_passes(self):
        validate_config(self.BASE)
