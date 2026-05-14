"""
MeshtasticBot — listens on a configured channel and replies to text messages.
Also runs an hourly background task that sends lightning and wind alerts via MET MetAlerts API.

Configuration is loaded from config.yaml. See config.yaml for available options.
"""

import time
import threading
import logging
import argparse
from datetime import datetime, timezone

import yaml
import meshtastic.serial_interface
import meshtastic.tcp_interface
import meshtastic.ble_interface
from pubsub import pub

from db import init_db, store_message, get_recent_messages

from weather import get_lightning_alerts, format_alert_message, \
    get_wind_alerts, format_wind_alert_message, \
    get_node_position, get_forecast, format_forecast_messages, \
    get_forecast_24h, format_forecast_24h_messages
from radio import get_radio_forecast, format_radio_messages
from bandplan import BANDPLAN, CALLING_FREQUENCIES, resolve_band, \
    format_bandplan_messages, format_calling_messages, \
    parse_frequency_mhz, lookup_frequency
from marine import format_mvhf_list_messages, format_mvhf_channel
from dummy import DummyInterface, run_dummy_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from constants import MAX_BYTES
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
    "Kommandoer [1/3]:\n"
    "/help - Vis hjelp\n"
    "/weather - 7-dagers varsel (GPS)\n"
    "/24hour|/24h - 24t timevarsel (GPS)",

    "Kommandoer [2/3]:\n"
    "/radio - HF/VHF båndkondisjon\n"
    "/bandplan <bånd> - Vis båndplan\n"
    "/bandplan_check <freq> - Sjekk frekvens\n"
    "/calling <bånd> - Anropsfrekvenser\n"
    "/mvhf [kanal] - Marin VHF kanaler\n"
    "/krslog [t] - Meldingslogg (std: 24t)",

    "Info [3/3]:\n"
    "- Kommandoer funker via DM\n"
    "- GPS må deles for værvarsler\n"
    "- Lynnvarsler og vindvarsler sendes automatisk",
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
    return None


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


def handle_radio_command(reply_fn) -> None:
    """Fetch amateur radio band conditions and send as multi-message reply."""
    data = get_radio_forecast()
    if data is None:
        reply_fn("Klarte ikke hente radiokondisjon fra HamQSL.")
        return
    messages = format_radio_messages(data)
    for i, msg in enumerate(messages):
        if i > 0:
            time.sleep(3)
        reply_fn(msg)


def handle_calling_command(text: str, reply_fn) -> None:
    """Parse band from command text and send calling frequencies."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        available = ", ".join(CALLING_FREQUENCIES.keys())
        reply_fn(f"Bruk: /calling <bånd>\nTilgjengelig: {available}")
        return

    band = resolve_band(parts[1])
    if band is None or band not in CALLING_FREQUENCIES:
        available = ", ".join(CALLING_FREQUENCIES.keys())
        reply_fn(f"Ukjent bånd '{parts[1]}'.\nTilgjengelig: {available}")
        return

    log.info(f"/calling {band} requested")
    messages = format_calling_messages(band)
    for i, msg in enumerate(messages):
        if i > 0:
            time.sleep(3)
        reply_fn(msg)


def handle_bandplan_check_command(text: str, reply_fn) -> None:
    """Parse a frequency from command text and reply with the allowed usage."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        reply_fn("Bruk: /bandplan_check <frekvens>\nEks: /bandplan_check 14.225\n     /bandplan_check 144300 kHz")
        return

    freq_mhz = parse_frequency_mhz(parts[1])
    if freq_mhz is None:
        reply_fn(f"Kunne ikke tolke frekvens: '{parts[1]}'.\nEks: 14.225 / 14.225 MHz / 14225 kHz")
        return

    result = lookup_frequency(freq_mhz)
    if result is None:
        reply_fn(f"{freq_mhz:.4f} MHz er ikke innenfor et amatørradio-bånd (IARU Region 1).")
        return

    band, freq_range, mode = result
    reply_fn(f"{freq_mhz:.4f} MHz → {band}\n{freq_range} MHz\n{mode}")
    log.info(f"/bandplan_check {freq_mhz} MHz -> {band} {mode}")


def handle_bandplan_command(text: str, reply_fn) -> None:
    """Parse band from command text and send band plan segments."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        available = ", ".join(BANDPLAN.keys())
        reply_fn(f"Bruk: /bandplan <bånd>\nTilgjengelig: {available}")
        return

    band = resolve_band(parts[1])
    if band is None:
        available = ", ".join(BANDPLAN.keys())
        reply_fn(f"Ukjent bånd '{parts[1]}'.\nTilgjengelig: {available}")
        return

    log.info(f"/bandplan {band} requested")
    messages = format_bandplan_messages(band)
    for i, msg in enumerate(messages):
        if i > 0:
            time.sleep(3)
        reply_fn(msg)


def handle_mvhf_command(text: str, reply_fn) -> None:
    """List key Marine VHF channels, or look up a specific channel."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) >= 2 and parts[1].strip():
        reply_fn(format_mvhf_channel(parts[1].strip()))
        return

    messages = format_mvhf_list_messages(groups=["Nød/DSC", "Havn/trafikk"])
    for i, msg in enumerate(messages):
        if i > 0:
            time.sleep(3)
        reply_fn(msg)


def handle_krslog_command(text: str, reply_fn, db_conn, log_channel: int) -> None:
    """Return recent messages from the log channel. Optional arg overrides the hour window."""
    parts = text.strip().split(maxsplit=1)
    hours = 24
    if len(parts) >= 2:
        try:
            hours = int(parts[1].strip())
            if hours < 1:
                raise ValueError
        except ValueError:
            reply_fn("Bruk: /krslog [antall timer]\nEks: /krslog 48")
            return

    if db_conn is None:
        reply_fn("Meldingslogg er ikke aktivert.")
        return

    rows = get_recent_messages(db_conn, log_channel, hours)
    if not rows:
        reply_fn(f"Ingen meldinger siste {hours}t.")
        return

    log.info(f"/krslog {hours}h — {len(rows)} message(s)")

    # Format into pages of up to ~5 messages each to stay within packet limits
    PAGE_SIZE = 5
    pages = []
    for i in range(0, len(rows), PAGE_SIZE):
        chunk = rows[i:i + PAGE_SIZE]
        lines = []
        for r in chunk:
            ts = r["received_at"][11:16]  # HH:MM from ISO timestamp
            lines.append(f"{ts} {r['sender_id']}: {r['text']}")
        pages.append("\n".join(lines))

    total_pages = len(pages)
    for i, page in enumerate(pages):
        if i > 0:
            time.sleep(3)
        header = f"Logg siste {hours}t [{i+1}/{total_pages}]:\n"
        reply_fn(header + page)


def make_receive_handler(interface, channel: int, db_conn=None, log_channel: int | None = None):
    def on_receive(packet, interface=interface):
        decoded = packet.get("decoded", {})
        text = decoded.get("text", "").strip()
        if not text:
            return

        sender = packet.get("fromId", "unknown")
        to_id = packet.get("toId", "^all")
        is_dm = to_id != "^all"
        pkt_channel = packet.get("channel", 0)

        if is_dm:
            log.info(f"[DM from {sender}]: {text}")
            def reply_fn(msg, _to=sender):
                log.info(f"[DM to {_to}]: {msg}")
                interface.sendText(msg, destinationId=_to, channelIndex=0)
        elif pkt_channel == channel:
            log.info(f"[ch{channel} from {sender}]: {text}")
            def reply_fn(msg, _ch=channel, _to=sender):
                log.info(f"[ch{_ch} to {_to}]: {msg}")
                interface.sendText(msg, channelIndex=_ch)
        else:
            return

        if db_conn is not None and not is_dm and pkt_channel == log_channel:
            packet_id = str(packet.get("id", ""))
            received_at = datetime.now(timezone.utc).isoformat()
            store_message(db_conn, packet_id, pkt_channel, sender, text, received_at)

        if text.lower().startswith("/help"):
            handle_help_command(reply_fn)
            return

        if text.lower().startswith("/weather"):
            handle_weather_command(interface, reply_fn, sender)
            return

        if text.lower().startswith("/24hour") or text.lower().startswith("/24h"):
            handle_24h_command(interface, reply_fn, sender)
            return

        if text.lower().startswith("/radio"):
            handle_radio_command(reply_fn)
            return

        if text.lower().startswith("/mvhf"):
            handle_mvhf_command(text, reply_fn)
            return

        if text.lower().startswith("/krslog"):
            handle_krslog_command(text, reply_fn, db_conn, log_channel)
            return

        if text.lower().startswith("/bandplan_check"):
            handle_bandplan_check_command(text, reply_fn)
            return

        if text.lower().startswith("/calling"):
            handle_calling_command(text, reply_fn)
            return

        if text.lower().startswith("/bandplan"):
            handle_bandplan_command(text, reply_fn)
            return

        reply = generate_reply(text, sender)
        if reply:
            reply_fn(reply)

    return on_receive


def weather_alert_loop(interface, channel: int, county: str, interval_seconds: int):
    """Background thread: checks for lightning and wind alerts and broadcasts new ones."""
    sent_lightning_ids: set[str] = set()
    sent_wind_ids: set[str] = set()

    def check_and_send():
        # Lightning alerts
        lightning_alerts = get_lightning_alerts(county)
        for alert in lightning_alerts:
            if alert["id"] not in sent_lightning_ids:
                msg = format_alert_message(alert)
                log.info(f"Sending lightning alert to ch{channel}: {msg}")
                interface.sendText(msg, channelIndex=channel)
                sent_lightning_ids.add(alert["id"])
        active_lightning_ids = {a["id"] for a in lightning_alerts}
        sent_lightning_ids.intersection_update(active_lightning_ids)

        # Wind alerts
        wind_alerts = get_wind_alerts(county)
        for alert in wind_alerts:
            if alert["id"] not in sent_wind_ids:
                msg = format_wind_alert_message(alert)
                log.info(f"Sending wind alert to ch{channel}: {msg}")
                interface.sendText(msg, channelIndex=channel)
                sent_wind_ids.add(alert["id"])
        active_wind_ids = {a["id"] for a in wind_alerts}
        sent_wind_ids.intersection_update(active_wind_ids)

    log.info(f"Weather alert task started (county={county}, interval={interval_seconds}s).")
    check_and_send()  # Run immediately on startup
    while True:
        time.sleep(interval_seconds)
        check_and_send()


def main():
    parser = argparse.ArgumentParser(description="MeshtasticBot")
    parser.add_argument("--dummy", action="store_true",
                        help="Run in dummy mode (no device required — interactive CLI)")
    parser.add_argument("--channel", type=int, default=None,
                        help="Override the channel index from config.yaml (dummy mode only)")
    args = parser.parse_args()

    cfg = load_config(CONFIG_FILE)
    channel = cfg.get("channel", 2)
    if args.channel is not None:
        channel = args.channel

    if args.dummy:
        interface = DummyInterface()
        log.info("Dummy mode active — no device connection.")
    else:
        interface = connect(cfg)

    msg_log_cfg = cfg.get("message_log", {})
    db_conn = None
    log_channel = None
    if msg_log_cfg.get("enabled", False):
        log_channel = int(msg_log_cfg.get("channel", 1))
        db_path = msg_log_cfg.get("db_path", "messages.db")
        db_conn = init_db(db_path)

    handler = make_receive_handler(interface, channel, db_conn=db_conn, log_channel=log_channel)

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

    if args.dummy:
        run_dummy_loop(handler, channel)
        interface.close()
    else:
        pub.subscribe(handler, "meshtastic.receive.text")
        log.info(f"Bot ready — listening on channel {channel}. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Shutting down.")
        finally:
            interface.close()


if __name__ == "__main__":
    main()
