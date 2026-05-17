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
