"""
Weather alert checker using the Norwegian Meteorological Institute (MET) API.
Fetches active MetAlerts for a given county and filters by event type.
"""

import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

METALERTS_URL = "https://api.met.no/weatherapi/metalerts/2.0/all.json"
USER_AGENT = "MeshtasticBot/1.0 github.com/chhenni/MeshtasticBot"

# MetAlerts event types that count as lightning alerts
LIGHTNING_EVENTS = {"lightning", "thunder", "thunderstorm"}


def fetch_alerts(county: str) -> list[dict]:
    """Fetch all active alerts for the given county code from MET API."""
    try:
        resp = requests.get(
            METALERTS_URL,
            params={"county": county},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("features", [])
    except requests.RequestException as e:
        log.error(f"Failed to fetch weather alerts: {e}")
        return []


def get_lightning_alerts(county: str) -> list[dict]:
    """Return active lightning alerts for the given county."""
    alerts = fetch_alerts(county)
    now = datetime.now(tz=timezone.utc)
    result = []

    for feature in alerts:
        props = feature.get("properties", {})

        if props.get("event", "").lower() not in LIGHTNING_EVENTS:
            continue

        # Skip expired alerts
        interval = feature.get("when", {}).get("interval", [])
        if len(interval) == 2:
            end = datetime.fromisoformat(interval[1])
            if end < now:
                continue

        result.append({
            "id": props.get("id", ""),
            "title": props.get("title", ""),
            "description": props.get("description", ""),
            "area": props.get("area", ""),
            "severity": props.get("severity", ""),
            "awareness_level": props.get("awareness_level", ""),
            "valid_until": interval[1] if len(interval) == 2 else None,
        })

    return result


def format_alert_message(alert: dict) -> str:
    """Format an alert into a short Meshtastic-friendly message (<200 chars)."""
    severity = alert["severity"].upper() if alert["severity"] else ""
    area = alert["area"]
    description = alert["description"]
    valid_until = ""

    if alert["valid_until"]:
        try:
            dt = datetime.fromisoformat(alert["valid_until"])
            valid_until = f" Gjelder til {dt.strftime('%d.%m %H:%M')} UTC."
        except ValueError:
            pass

    msg = f"⚡ LYN-VARSEL [{severity}]: {area}. {description}{valid_until}"
    # Truncate to 200 chars to stay well within Meshtastic MTU
    if len(msg) > 200:
        msg = msg[:197] + "..."
    return msg
