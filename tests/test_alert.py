"""
Tests for handle_alert_command in commands.py.
No network calls are made; get_lightning_alerts and get_wind_alerts are patched.
"""

from unittest.mock import patch

from commands import handle_alert_command

DUMMY_LIGHTNING = {
    "id": "lightning-1",
    "area": "Agder",
    "description": "Tordenbyger med lyn.",
    "severity": "Moderate",
    "valid_until": "2099-01-01T12:00:00+00:00",
}

DUMMY_WIND = {
    "id": "wind-1",
    "area": "Agder",
    "description": "Sterk kuling, vestlig 20 m/s.",
    "severity": "High",
    "valid_until": "2099-01-01T18:00:00+00:00",
}


class TestAlertCommand:
    def _run(self, lightning, wind, county="42"):
        replies = []
        ctx = {"county": county, "interface": None, "sender": None, "db_conn": None, "log_channel": None}
        with patch("commands.get_lightning_alerts", return_value=lightning), \
             patch("commands.get_wind_alerts", return_value=wind), \
             patch("commands.time.sleep"):
            handle_alert_command("/alert", replies.append, ctx)
        return replies

    def test_no_active_alerts(self):
        replies = self._run([], [])
        assert len(replies) == 1
        assert "Ingen aktive varsler" in replies[0]
        assert "✅" in replies[0]

    def test_lightning_alert(self):
        replies = self._run([DUMMY_LIGHTNING], [])
        assert replies[0].startswith("⚠️")
        assert "1" in replies[0]
        assert any("⚡" in r for r in replies)
        assert any("Agder" in r for r in replies)

    def test_wind_alert(self):
        replies = self._run([], [DUMMY_WIND])
        assert replies[0].startswith("⚠️")
        assert any("💨" in r for r in replies)
        assert any("Agder" in r for r in replies)

    def test_both_alert_types(self):
        replies = self._run([DUMMY_LIGHTNING], [DUMMY_WIND])
        assert "2" in replies[0]
        assert any("⚡" in r for r in replies)
        assert any("💨" in r for r in replies)

    def test_multiple_alerts_count(self):
        replies = self._run([DUMMY_LIGHTNING, DUMMY_LIGHTNING], [DUMMY_WIND])
        assert "3" in replies[0]

    def test_no_county_configured(self):
        replies = []
        ctx = {"county": None, "interface": None, "sender": None, "db_conn": None, "log_channel": None}
        handle_alert_command("/alert", replies.append, ctx)
        assert len(replies) == 1
        assert "ikke konfigurert" in replies[0]

    def test_empty_county_string(self):
        replies = []
        ctx = {"county": "", "interface": None, "sender": None, "db_conn": None, "log_channel": None}
        handle_alert_command("/alert", replies.append, ctx)
        assert "ikke konfigurert" in replies[0]
