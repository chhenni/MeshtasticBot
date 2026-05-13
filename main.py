"""
MeshtasticBot — listens on a configured channel and replies to text messages.
Also runs an hourly background task that sends lightning alerts via MET MetAlerts API.

Configuration is loaded from config.yaml. See config.yaml for available options.
"""

import time
import threading
import logging

import yaml
import meshtastic.serial_interface
import meshtastic.tcp_interface
import meshtastic.ble_interface
from pubsub import pub

from weather import get_lightning_alerts, format_alert_message, \
    get_node_position, get_forecast, format_forecast_messages, \
    get_forecast_24h, format_forecast_24h_messages

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CONFIG_FILE = "config.yaml"


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def connect(cfg: dict):
    """Create and return a Meshtastic interface based on config."""
    conn = cfg.get("connection", {})
    kind = conn.get("type", "serial")

    if kind == "serial":
        port = conn.get("port")  # None = auto-detect
        log.info(f"Connecting via serial (port={port or 'auto'})...")
        return meshtastic.serial_interface.SerialInterface(devPath=port)

    if kind == "tcp":
        host = conn["host"]
        log.info(f"Connecting via TCP ({host})...")
        return meshtastic.tcp_interface.TCPInterface(hostname=host)

    if kind == "ble":
        address = conn.get("address")
        log.info(f"Connecting via BLE (address={address or 'auto'})...")
        return meshtastic.ble_interface.BLEInterface(address=address)

    raise ValueError(f"Unknown connection type: {kind!r}")


HELP_MESSAGES = [
    "MeshtasticBot kommandoer [1/2]:\n"
    "/help - Vis denne hjelpen\n"
    "/weather - 7-dagers varsel (krever GPS)\n"
    "/24hour (/24h) - Timevarsel neste 24t (krever GPS)",

    "MeshtasticBot info [2/2]:\n"
    "- Send kommandoer som DM\n"
    "- GPS-posisjon må deles for værvarsler\n"
]


def handle_help_command(reply_fn) -> None:
    for i, msg in enumerate(HELP_MESSAGES):
        if i > 0:
            time.sleep(2)
        reply_fn(msg)


def generate_reply(text: str, sender_id: str) -> str | None:
    """
    Return a reply string, or None to stay silent.
    Customize this function to implement your bot logic.
    Note: commands are handled separately in make_receive_handler.
    """
    return f"Echo from bot: {text}"


def handle_weather_command(interface, reply_fn, sender_id: str) -> None:
    """Look up sender position, fetch 7-day forecast, send multi-message reply."""
    pos = get_node_position(interface, sender_id)
    if pos is None:
        reply_fn("Ingen GPS-posisjon funnet for din node. Del posisjon og prøv igjen.")
        return

    lat, lon = pos
    log.info(f"/weather requested by {sender_id} at ({lat}, {lon})")
    forecast = get_forecast(lat, lon)

    if forecast is None:
        reply_fn("Klarte ikke hente varsel fra yr.no.")
        return

    messages = format_forecast_messages(forecast, lat, lon)
    for i, msg in enumerate(messages):
        if i > 0:
            time.sleep(3)
        reply_fn(msg)
        log.info(f"/weather reply {i + 1}/{len(messages)}: {msg}")


def handle_24h_command(interface, reply_fn, sender_id: str) -> None:
    """Look up sender position, fetch 24-hour forecast, send multi-message reply."""
    pos = get_node_position(interface, sender_id)
    if pos is None:
        reply_fn("Ingen GPS-posisjon funnet for din node. Del posisjon og prøv igjen.")
        return

    lat, lon = pos
    log.info(f"/24hour requested by {sender_id} at ({lat}, {lon})")
    forecast = get_forecast_24h(lat, lon)

    if forecast is None:
        reply_fn("Klarte ikke hente varsel fra yr.no.")
        return

    messages = format_forecast_24h_messages(forecast, lat, lon)
    for i, msg in enumerate(messages):
        if i > 0:
            time.sleep(3)
        reply_fn(msg)
        log.info(f"/24hour reply {i + 1}/{len(messages)}: {msg}")


def make_receive_handler(interface, channel: int):
    def on_receive(packet, interface=interface):
        decoded = packet.get("decoded", {})
        text = decoded.get("text", "").strip()
        if not text:
            return

        sender = packet.get("fromId", "unknown")
        to_id = packet.get("toId", "^all")
        is_dm = to_id != "^all"

        if is_dm:
            log.info(f"[DM] {sender}: {text}")
            reply_fn = lambda msg: interface.sendText(msg, destinationId=sender, channelIndex=0)
        elif packet.get("channel", 0) == channel:
            log.info(f"[ch{channel}] {sender}: {text}")
            reply_fn = lambda msg: interface.sendText(msg, channelIndex=channel)
        else:
            return

        if text.lower().startswith("/help"):
            handle_help_command(reply_fn)
            return

        if text.lower().startswith("/weather"):
            handle_weather_command(interface, reply_fn, sender)
            return

        if text.lower().startswith("/24hour") or text.lower().startswith("/24h"):
            handle_24h_command(interface, reply_fn, sender)
            return

        reply = generate_reply(text, sender)
        if reply:
            reply_fn(reply)
            log.info(f"→ {reply}")

    return on_receive


def weather_alert_loop(interface, channel: int, county: str, interval_seconds: int):
    """Background thread: checks for lightning alerts and broadcasts new ones."""
    sent_ids: set[str] = set()

    def check_and_send():
        alerts = get_lightning_alerts(county)
        new_alerts = [a for a in alerts if a["id"] not in sent_ids]

        for alert in new_alerts:
            msg = format_alert_message(alert)
            log.info(f"Sending lightning alert to ch{channel}: {msg}")
            interface.sendText(msg, channelIndex=channel)
            sent_ids.add(alert["id"])

        # Prune IDs of alerts no longer returned by API to avoid unbounded growth
        active_ids = {a["id"] for a in alerts}
        sent_ids.intersection_update(active_ids)

    log.info(f"Weather alert task started (county={county}, interval={interval_seconds}s).")
    check_and_send()  # Run immediately on startup
    while True:
        time.sleep(interval_seconds)
        check_and_send()


def main():
    cfg = load_config(CONFIG_FILE)
    channel = cfg.get("channel", 2)

    interface = connect(cfg)
    handler = make_receive_handler(interface, channel)
    pub.subscribe(handler, "meshtastic.receive.text")
    log.info(f"Bot ready — listening on channel {channel}. Press Ctrl+C to stop.")

    weather_cfg = cfg.get("weather", {})
    if weather_cfg.get("enabled", True):
        county = str(weather_cfg.get("county", "42"))
        interval = weather_cfg.get("interval_seconds", 3600)
        t = threading.Thread(
            target=weather_alert_loop,
            args=(interface, channel, county, interval),
            daemon=True,
        )
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down.")
    finally:
        interface.close()


if __name__ == "__main__":
    main()
