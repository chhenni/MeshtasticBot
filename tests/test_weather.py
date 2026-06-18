"""
Tests for weather.py — formatting functions and alert filtering.
No network calls are made; all tests use synthetic data.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from constants import MAX_BYTES
from weather import (
    format_alert_message,
    format_forecast_24h_messages,
    format_forecast_messages,
    format_wind_alert_message,
    get_lightning_alerts,
    get_wind_alerts,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def make_daily_forecast(n=7):
    today = date.today()
    days = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]
    return [
        {
            "date": today + timedelta(days=i),
            "day_name": days[(today.weekday() + i) % 7],
            "temp_min": 10 + i,
            "temp_max": 18 + i,
            "precip": round(i * 0.5, 1),
            "symbol": "☀️ Sol",
            "wind": 3.5,
        }
        for i in range(n)
    ]


def make_hourly_forecast(n=24):
    now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [
        {
            "dt": now + timedelta(hours=i),
            "hour": (now + timedelta(hours=i)).strftime("%H"),
            "temp": 15 + (i % 5),
            "precip": 0.0 if i % 3 else 1.2,
            "symbol": "☀️ Sol",
            "wind": 4.0,
        }
        for i in range(n)
    ]


def make_alert(event="lightning", expired=False):
    now = datetime.now(tz=timezone.utc)
    end = (now - timedelta(hours=1)) if expired else (now + timedelta(hours=2))
    return {
        "type": "Feature",
        "properties": {
            "id": "test-id-1",
            "event": event,
            "title": "Test alert",
            "description": "Kraftig tordenvær",
            "area": "Agder",
            "severity": "Moderate",
            "awareness_level": "2; yellow; Moderate",
        },
        "when": {
            "interval": [
                (now - timedelta(hours=1)).isoformat(),
                end.isoformat(),
            ]
        },
    }


# ---------------------------------------------------------------------------
# format_forecast_messages
# ---------------------------------------------------------------------------

class TestFormatForecastMessages:
    def test_byte_safe(self):
        forecast = make_daily_forecast(7)
        for msg in format_forecast_messages(forecast, 59.91, 10.75):
            assert len(msg.encode("utf-8")) <= MAX_BYTES

    def test_single_page_no_counter(self):
        forecast = make_daily_forecast(1)
        messages = format_forecast_messages(forecast, 59.91, 10.75)
        assert len(messages) == 1
        assert not messages[0].startswith("[")

    def test_multi_page_has_counter(self):
        forecast = make_daily_forecast(7)
        messages = format_forecast_messages(forecast, 59.91, 10.75)
        if len(messages) > 1:
            assert messages[0].startswith("[1/")


# ---------------------------------------------------------------------------
# format_forecast_24h_messages
# ---------------------------------------------------------------------------

class TestFormatForecast24hMessages:
    def test_byte_safe(self):
        forecast = make_hourly_forecast(24)
        for msg in format_forecast_24h_messages(forecast, 59.91, 10.75):
            assert len(msg.encode("utf-8")) <= MAX_BYTES

    def test_contains_hours(self):
        forecast = make_hourly_forecast(3)
        combined = "\n".join(format_forecast_24h_messages(forecast, 59.91, 10.75))
        for h in forecast:
            assert h["hour"] + "h" in combined


# ---------------------------------------------------------------------------
# format_alert_message / format_wind_alert_message
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_alert():
    return {
        "id": "abc123",
        "title": "Farevarsel for lyn",
        "description": "Kraftig tordenvær med mye lyn.",
        "area": "Agder",
        "severity": "Moderate",
        "awareness_level": "2; yellow; Moderate",
        "valid_until": (datetime.now(tz=timezone.utc) + timedelta(hours=3)).isoformat(),
    }


class TestFormatAlertMessage:
    def test_returns_list(self, sample_alert):
        assert isinstance(format_alert_message(sample_alert), list)

    def test_within_byte_limit(self, sample_alert):
        for page in format_alert_message(sample_alert):
            assert len(page.encode("utf-8")) <= MAX_BYTES

    def test_contains_severity(self, sample_alert):
        full = " ".join(format_alert_message(sample_alert))
        assert "MODERATE" in full

    def test_contains_area(self, sample_alert):
        full = " ".join(format_alert_message(sample_alert))
        assert "Agder" in full

    def test_lightning_prefix(self, sample_alert):
        assert format_alert_message(sample_alert)[0].startswith("⚡")

    def test_no_valid_until(self, sample_alert):
        sample_alert["valid_until"] = None
        full = " ".join(format_alert_message(sample_alert))
        assert "Gjelder til" not in full

    def test_long_description_not_truncated(self):
        long_desc = "Dette er en veldig lang beskrivelse av farevarsel. " * 10
        alert = {
            "id": "x",
            "description": long_desc,
            "area": "Agder",
            "severity": "Extreme",
            "valid_until": None,
        }
        pages = format_alert_message(alert)
        full = " ".join(pages)
        assert "..." not in full
        assert long_desc.strip() in full
        for page in pages:
            assert len(page.encode("utf-8")) <= MAX_BYTES

    def test_short_message_is_single_page(self, sample_alert):
        pages = format_alert_message(sample_alert)
        assert len(pages) == 1


class TestFormatWindAlertMessage:
    def test_returns_list(self, sample_alert):
        assert isinstance(format_wind_alert_message(sample_alert), list)

    def test_within_byte_limit(self, sample_alert):
        for page in format_wind_alert_message(sample_alert):
            assert len(page.encode("utf-8")) <= MAX_BYTES

    def test_wind_prefix(self, sample_alert):
        assert format_wind_alert_message(sample_alert)[0].startswith("💨")

    def test_long_description_not_truncated(self):
        long_desc = "Svært sterk storm med ekstreme vindkast langs kysten. " * 8
        alert = {
            "id": "y",
            "description": long_desc,
            "area": "Vestland",
            "severity": "Extreme",
            "valid_until": None,
        }
        pages = format_wind_alert_message(alert)
        full = " ".join(pages)
        assert "..." not in full
        assert long_desc.strip() in full
        for page in pages:
            assert len(page.encode("utf-8")) <= MAX_BYTES


# ---------------------------------------------------------------------------
# Alert filtering (get_lightning_alerts / get_wind_alerts)
# Uses monkeypatching to avoid real HTTP calls
# ---------------------------------------------------------------------------

class TestAlertFiltering:
    def test_lightning_filters_event_type(self, monkeypatch):
        features = [
            make_alert("lightning"),
            make_alert("wind"),
            make_alert("rain"),
        ]
        monkeypatch.setattr("weather.fetch_alerts", lambda county: features)
        alerts = get_lightning_alerts("42")
        assert len(alerts) == 1

    def test_wind_filters_event_type(self, monkeypatch):
        features = [make_alert("wind"), make_alert("gale"), make_alert("lightning")]
        monkeypatch.setattr("weather.fetch_alerts", lambda county: features)
        alerts = get_wind_alerts("42")
        assert len(alerts) == 2

    def test_expired_alerts_excluded(self, monkeypatch):
        features = [make_alert("lightning", expired=True)]
        monkeypatch.setattr("weather.fetch_alerts", lambda county: features)
        assert get_lightning_alerts("42") == []

    def test_active_alerts_included(self, monkeypatch):
        features = [make_alert("lightning", expired=False)]
        monkeypatch.setattr("weather.fetch_alerts", lambda county: features)
        assert len(get_lightning_alerts("42")) == 1
