"""
Tests for connect_with_retry — exponential backoff reconnect logic.
"""

from unittest.mock import MagicMock, patch

from main import connect_with_retry


class TestConnectWithRetry:
    def test_succeeds_on_first_attempt(self):
        cfg = {"connection": {"type": "serial"}}
        mock_iface = MagicMock()
        with patch("main.connect", return_value=mock_iface) as mock_connect:
            result = connect_with_retry(cfg)
        assert result is mock_iface
        assert mock_connect.call_count == 1

    def test_retries_on_failure_then_succeeds(self):
        cfg = {"connection": {"type": "serial"}}
        mock_iface = MagicMock()
        with patch("main.connect", side_effect=[Exception("fail"), mock_iface]) as mock_connect:
            with patch("main.time.sleep"):  # skip actual sleeps
                result = connect_with_retry(cfg, base_delay=0.01)
        assert result is mock_iface
        assert mock_connect.call_count == 2

    def test_retries_multiple_times(self):
        cfg = {"connection": {"type": "serial"}}
        mock_iface = MagicMock()
        failures = [Exception("fail")] * 4
        with patch("main.connect", side_effect=failures + [mock_iface]) as mock_connect:
            with patch("main.time.sleep"):
                result = connect_with_retry(cfg, base_delay=0.01)
        assert result is mock_iface
        assert mock_connect.call_count == 5

    def test_uses_exponential_backoff(self):
        cfg = {"connection": {"type": "serial"}}
        mock_iface = MagicMock()
        sleep_calls = []
        with patch("main.connect", side_effect=[Exception(), Exception(), mock_iface]):
            with patch("main.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
                connect_with_retry(cfg, base_delay=1.0)
        # First retry: ~1s, second retry: ~2s (exponential)
        assert len(sleep_calls) == 2
        assert sleep_calls[1] > sleep_calls[0]

    def test_caps_delay_at_max(self):
        cfg = {"connection": {"type": "serial"}}
        mock_iface = MagicMock()
        sleep_calls = []
        failures = [Exception()] * 10
        with patch("main.connect", side_effect=failures + [mock_iface]):
            with patch("main.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
                connect_with_retry(cfg, base_delay=1.0, max_delay=30.0)
        assert all(s <= 30.0 for s in sleep_calls)

    def test_logs_each_failure(self):
        cfg = {"connection": {"type": "serial"}}
        mock_iface = MagicMock()
        with patch("main.connect", side_effect=[Exception("port not found"), mock_iface]):
            with patch("main.time.sleep"):
                with patch("main.log") as mock_log:
                    connect_with_retry(cfg, base_delay=0.01)
        # Should have logged the error at least once
        assert mock_log.error.call_count >= 1 or mock_log.warning.call_count >= 1
