"""Tests for graceful shutdown via shutdown_event."""

import threading
from unittest.mock import MagicMock, patch


class TestDbPurgeLoopShutdown:
    def test_loop_exits_when_event_set(self):
        from main import db_purge_loop

        event = threading.Event()
        conn = MagicMock()
        t = threading.Thread(
            target=db_purge_loop,
            args=(conn, 365, event),
            kwargs={"interval_seconds": 60},
            daemon=True,
        )
        t.start()
        event.set()
        t.join(timeout=2)
        assert not t.is_alive()

    def test_loop_calls_purge_on_start(self):
        from main import db_purge_loop

        event = threading.Event()
        conn = MagicMock()
        with patch("main.purge_old_messages") as mock_purge:
            event.set()  # exit immediately after first run
            t = threading.Thread(
                target=db_purge_loop,
                args=(conn, 365, event),
                kwargs={"interval_seconds": 60},
                daemon=True,
            )
            t.start()
            t.join(timeout=2)
        mock_purge.assert_called_once()


class TestNodeSyncLoopShutdown:
    def test_loop_exits_when_event_set(self):
        from main import node_sync_loop

        event = threading.Event()
        interface = MagicMock()
        interface.nodes = {}
        db_conn = MagicMock()
        t = threading.Thread(
            target=node_sync_loop,
            args=(interface, db_conn, event),
            kwargs={"interval_seconds": 60},
            daemon=True,
        )
        t.start()
        event.set()
        t.join(timeout=2)
        assert not t.is_alive()


class TestWeatherAlertLoopShutdown:
    def test_loop_exits_when_event_set(self):
        from main import weather_alert_loop

        event = threading.Event()
        interface = MagicMock()
        with (
            patch("main.get_lightning_alerts", return_value=[]),
            patch("main.get_wind_alerts", return_value=[]),
        ):
            t = threading.Thread(
                target=weather_alert_loop,
                args=(interface, 0, "42", 60, event),
                daemon=True,
            )
            t.start()
            event.set()
            t.join(timeout=2)
        assert not t.is_alive()


class TestShutdownEventSignal:
    def test_sigterm_sets_shutdown_event(self):
        """SIGTERM handler must set the shutdown_event."""
        import signal

        from main import _make_signal_handler

        event = threading.Event()
        handler = _make_signal_handler(event)
        handler(signal.SIGTERM, None)
        assert event.is_set()

    def test_sigint_sets_shutdown_event(self):
        import signal

        from main import _make_signal_handler

        event = threading.Event()
        handler = _make_signal_handler(event)
        handler(signal.SIGINT, None)
        assert event.is_set()
