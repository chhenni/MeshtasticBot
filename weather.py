"""
Weather utilities:
- Lightning alert checker via MET MetAlerts API
- 7-day location forecast via yr.no locationforecast API
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

METALERTS_URL = "https://api.met.no/weatherapi/metalerts/2.0/all.json"
FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
USER_AGENT = "MeshtasticBot/1.0 github.com/chhenni/MeshtasticBot"

# MetAlerts event types that count as lightning alerts
LIGHTNING_EVENTS = {"lightning", "thunder", "thunderstorm"}

_DAYS_NO = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]

_SYMBOL_MAP = {
    "clearsky": "Sol",
    "fair": "Lettskyet",
    "partlycloudy": "Delvis skyet",
    "cloudy": "Overskyet",
    "fog": "Tåke",
    "lightrainshowers": "Lett regnbyger",
    "rainshowers": "Regnbyger",
    "heavyrainshowers": "Kraftige regnbyger",
    "lightrain": "Lett regn",
    "rain": "Regn",
    "heavyrain": "Kraftig regn",
    "lightsleetshowers": "Lett sluddbyger",
    "sleetshowers": "Sluddbyger",
    "lightsleet": "Lett sludd",
    "sleet": "Sludd",
    "heavysleet": "Kraftig sludd",
    "lightsnowshowers": "Lett snøbyger",
    "snowshowers": "Snøbyger",
    "lightsnow": "Lett snø",
    "snow": "Snø",
    "heavysnow": "Kraftig snø",
    "lightrainshowersandthunder": "Lett regn/lyn",
    "rainshowersandthunder": "Regnbyger/lyn",
    "lightrainandthunder": "Lett regn/lyn",
    "rainandthunder": "Regn/lyn",
    "heavyrainandthunder": "Kraftig regn/lyn",
    "snowandthunder": "Snø/lyn",
    "sleetandthunder": "Sludd/lyn",
}


def _symbol_to_no(symbol_code: str) -> str:
    """Convert yr.no symbol code to a Norwegian description."""
    base = symbol_code
    for suffix in ("_polartwilight", "_night", "_day"):
        if symbol_code.endswith(suffix):
            base = symbol_code[: -len(suffix)]
            break
    return _SYMBOL_MAP.get(base, base)


# ---------------------------------------------------------------------------
# Node position helpers
# ---------------------------------------------------------------------------

def get_node_position(interface, node_id: str) -> tuple[float, float] | None:
    """Return (lat, lon) for a node, or None if position is unknown."""
    node = (interface.nodes or {}).get(node_id)
    if not node:
        return None
    pos = node.get("position", {})
    lat = pos.get("latitude")
    lon = pos.get("longitude")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


# ---------------------------------------------------------------------------
# 7-day forecast
# ---------------------------------------------------------------------------

def get_forecast(lat: float, lon: float) -> list[dict] | None:
    """
    Fetch and return a 7-day daily forecast from yr.no.
    Each entry: {date, day_name, temp_min, temp_max, precip, symbol, wind}
    Returns None on error.
    """
    try:
        resp = requests.get(
            FORECAST_URL,
            params={"lat": round(lat, 4), "lon": round(lon, 4)},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        timeseries = resp.json()["properties"]["timeseries"]
    except (requests.RequestException, KeyError, ValueError) as e:
        log.error(f"Failed to fetch forecast: {e}")
        return None

    # Group hourly entries by UTC date
    by_day: dict = defaultdict(list)
    for entry in timeseries:
        dt = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
        by_day[dt.date()].append((dt, entry))

    today = datetime.now(tz=timezone.utc).date()
    days = sorted(d for d in by_day if d >= today)[:7]

    result = []
    for day in days:
        entries = by_day[day]

        temps = [
            e["data"]["instant"]["details"]["air_temperature"]
            for _, e in entries
            if "air_temperature" in e["data"]["instant"]["details"]
        ]
        # Sum precipitation: use 1h entries where available, fall back to 6h for later days
        precip = 0.0
        for _, e in entries:
            data = e["data"]
            if "next_1_hours" in data:
                precip += data["next_1_hours"]["details"].get("precipitation_amount", 0.0)
            elif "next_6_hours" in data:
                precip += data["next_6_hours"]["details"].get("precipitation_amount", 0.0)

        # Use noon entry for representative symbol + wind; fall back to midpoint
        noon = [(dt, e) for dt, e in entries if dt.hour == 12]
        _, rep = noon[0] if noon else entries[len(entries) // 2]

        symbol = ""
        for window in ("next_12_hours", "next_6_hours", "next_1_hours"):
            sym = rep["data"].get(window, {}).get("summary", {}).get("symbol_code", "")
            if sym:
                symbol = _symbol_to_no(sym)
                break

        wind = rep["data"]["instant"]["details"].get("wind_speed", 0.0)

        result.append({
            "date": day,
            "day_name": _DAYS_NO[day.weekday()],
            "temp_min": round(min(temps)) if temps else None,
            "temp_max": round(max(temps)) if temps else None,
            "precip": round(precip, 1),
            "symbol": symbol,
            "wind": round(wind, 1),
        })

    return result


def format_forecast_messages(forecast: list[dict], lat: float, lon: float) -> list[str]:
    """
    Split a 7-day forecast into a list of Meshtastic-safe messages (<200 chars each).
    Each message is labelled [part/total] so the receiver knows more are coming.
    """
    MAX_LEN = 185  # leave room for part label

    header = f"Varsel {lat:.2f}N {lon:.2f}E:"
    lines = []
    for d in forecast:
        temp = (
            f"{d['temp_min']}-{d['temp_max']}C"
            if d["temp_min"] is not None
            else "?C"
        )
        precip = f" {d['precip']}mm" if d["precip"] > 0 else ""
        lines.append(
            f"{d['day_name']} {d['date'].strftime('%d.%m')}: "
            f"{d['symbol']}, {temp}, {d['wind']}m/s{precip}"
        )

    # Build pages without part labels first
    pages: list[str] = []
    current = header
    for line in lines:
        candidate = current + "\n" + line
        if len(candidate) > MAX_LEN and current != header:
            pages.append(current)
            current = line
        else:
            current = candidate
    if current:
        pages.append(current)

    # Prepend [N/total] only when there are multiple pages
    total = len(pages)
    if total == 1:
        return pages
    return [f"[{i + 1}/{total}] {page}" for i, page in enumerate(pages)]


# ---------------------------------------------------------------------------
# Lightning alerts
# ---------------------------------------------------------------------------

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
    if len(msg) > 200:
        msg = msg[:197] + "..."
    return msg
