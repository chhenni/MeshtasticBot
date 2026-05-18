"""
Tests for SIGHUP config reload (issue #14).
"""

import os
import signal
import tempfile
from datetime import datetime, timezone

import pytest
import yaml

from main import _make_sighup_handler


def _write_config(path: str, cfg: dict) -> None:
    with open(path, "w") as f:
        yaml.dump(cfg, f)


BASE_CFG = {
    "connection": {"type": "serial"},
    "weather": {"enabled": True, "county": "03"},
    "rate_limit": {"bucket_size": 5.0, "refill_rate": 0.1},
    "admin": {"username": "admin", "password": "secret"},
}


@pytest.fixture
def config_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(BASE_CFG, f)
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def bot_state():
    return {
        "start_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "county": "03",
        "bucket_size": 5.0,
        "refill_rate": 0.1,
        "admin_username": "admin",
        "admin_password": "secret",
        "connected": True,
    }


class TestSighupHandler:
    def test_handler_is_callable(self, config_file, bot_state):
        handler = _make_sighup_handler(config_file, bot_state)
        assert callable(handler)

    def test_updates_county_in_bot_state(self, config_file, bot_state):
        handler = _make_sighup_handler(config_file, bot_state)
        _write_config(config_file, {**BASE_CFG, "weather": {"enabled": True, "county": "15"}})
        handler(signal.SIGHUP, None)
        assert bot_state["county"] == "15"

    def test_updates_bucket_size_in_bot_state(self, config_file, bot_state):
        handler = _make_sighup_handler(config_file, bot_state)
        new_cfg = {**BASE_CFG, "rate_limit": {"bucket_size": 10.0, "refill_rate": 0.1}}
        _write_config(config_file, new_cfg)
        handler(signal.SIGHUP, None)
        assert bot_state["bucket_size"] == 10.0

    def test_updates_refill_rate_in_bot_state(self, config_file, bot_state):
        handler = _make_sighup_handler(config_file, bot_state)
        new_cfg = {**BASE_CFG, "rate_limit": {"bucket_size": 5.0, "refill_rate": 0.5}}
        _write_config(config_file, new_cfg)
        handler(signal.SIGHUP, None)
        assert bot_state["refill_rate"] == 0.5

    def test_updates_admin_credentials(self, config_file, bot_state):
        handler = _make_sighup_handler(config_file, bot_state)
        new_cfg = {**BASE_CFG, "admin": {"username": "newadmin", "password": "newpass"}}
        _write_config(config_file, new_cfg)
        handler(signal.SIGHUP, None)
        assert bot_state["admin_username"] == "newadmin"
        assert bot_state["admin_password"] == "newpass"

    def test_invalid_config_does_not_update_state(self, config_file, bot_state):
        handler = _make_sighup_handler(config_file, bot_state)
        # Write an invalid config (bad county)
        bad_cfg = {**BASE_CFG, "weather": {"enabled": True, "county": "INVALID"}}
        _write_config(config_file, bad_cfg)
        handler(signal.SIGHUP, None)
        # Original county should be preserved
        assert bot_state["county"] == "03"

    def test_missing_file_does_not_crash(self, bot_state):
        handler = _make_sighup_handler("/nonexistent/path.yaml", bot_state)
        handler(signal.SIGHUP, None)  # should log error, not raise
        assert bot_state["county"] == "03"  # unchanged

    def test_county_unchanged_when_weather_disabled(self, config_file, bot_state):
        handler = _make_sighup_handler(config_file, bot_state)
        new_cfg = {**BASE_CFG, "weather": {"enabled": False, "county": "99"}}
        _write_config(config_file, new_cfg)
        handler(signal.SIGHUP, None)
        # Weather disabled — county should be cleared
        assert bot_state["county"] == ""
