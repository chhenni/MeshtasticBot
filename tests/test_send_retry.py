"""Tests for send_text_with_retry — wraps sendText with up to 5 retries."""

from unittest.mock import MagicMock, patch


class TestSendTextWithRetry:
    def test_succeeds_on_first_attempt(self):
        from main import send_text_with_retry

        iface = MagicMock()
        send_text_with_retry(iface, "hello", channelIndex=0)
        iface.sendText.assert_called_once_with("hello", channelIndex=0)

    def test_succeeds_on_second_attempt(self):
        from meshtastic.mesh_interface import MeshInterface

        from main import send_text_with_retry

        iface = MagicMock()
        iface.sendText.side_effect = [MeshInterface.MeshInterfaceError("busy"), None]
        with patch("main.time.sleep"):
            send_text_with_retry(iface, "hello", channelIndex=0)
        assert iface.sendText.call_count == 2

    def test_retries_up_to_five_times(self):
        from meshtastic.mesh_interface import MeshInterface

        from main import send_text_with_retry

        iface = MagicMock()
        iface.sendText.side_effect = MeshInterface.MeshInterfaceError("always busy")
        with patch("main.time.sleep"):
            send_text_with_retry(iface, "hello", channelIndex=0)
        assert iface.sendText.call_count == 5

    def test_succeeds_on_fifth_attempt(self):
        from meshtastic.mesh_interface import MeshInterface

        from main import send_text_with_retry

        iface = MagicMock()
        err = MeshInterface.MeshInterfaceError("busy")
        iface.sendText.side_effect = [err, err, err, err, None]
        with patch("main.time.sleep"):
            send_text_with_retry(iface, "hello", channelIndex=0)
        assert iface.sendText.call_count == 5

    def test_exponential_backoff_delays(self):
        from meshtastic.mesh_interface import MeshInterface

        from main import send_text_with_retry

        iface = MagicMock()
        iface.sendText.side_effect = MeshInterface.MeshInterfaceError("busy")
        with patch("main.time.sleep") as mock_sleep:
            send_text_with_retry(iface, "hello", channelIndex=0)
        delays = [c.args[0] for c in mock_sleep.call_args_list]
        # Each delay should be >= previous (exponential growth)
        assert len(delays) == 4  # 4 sleeps between 5 attempts
        assert delays == sorted(delays)

    def test_passes_kwargs_to_sendtext(self):
        from main import send_text_with_retry

        iface = MagicMock()
        send_text_with_retry(iface, "dm", destinationId="!abc", channelIndex=0)
        iface.sendText.assert_called_once_with("dm", destinationId="!abc", channelIndex=0)

    def test_logs_warning_on_failure(self, caplog):
        import logging

        from meshtastic.mesh_interface import MeshInterface

        from main import send_text_with_retry

        iface = MagicMock()
        iface.sendText.side_effect = MeshInterface.MeshInterfaceError("oops")
        with patch("main.time.sleep"):
            with caplog.at_level(logging.WARNING, logger="main"):
                send_text_with_retry(iface, "hello", channelIndex=0)
        assert any("sendText" in r.message or "oops" in r.message for r in caplog.records)
