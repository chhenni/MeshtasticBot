"""
MeshtasticBot — listens on a configured channel and replies to text messages.
Also runs background tasks for weather alerts and database maintenance.

Configuration is loaded from config.yaml. See config.yaml for available options.
"""

import argparse
import logging
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

import meshtastic.ble_interface
import meshtastic.serial_interface
import meshtastic.tcp_interface
import yaml
from pubsub import pub

from commands import COMMANDS
from db import init_db, purge_old_messages, store_message
from dummy import DummyInterface, run_dummy_loop
from weather import (
    format_alert_message,
    format_wind_alert_message,
    get_lightning_alerts,
    get_wind_alerts,
)
from web import start_web_server

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
        port = conn.get("port")
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


def make_receive_handler(
    interface,
    channel: int,
    db_conn=None,
    log_channel: int | None = None,
    bot_state: dict | None = None,
):
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
            reply_fn = None

        # Store every received message. DMs are stored with channel = -1.
        if db_conn is not None:
            raw_id = packet.get("id")
            packet_id = str(raw_id) if raw_id else str(uuid4())
            received_at = datetime.now(timezone.utc).isoformat()
            store_channel = -1 if is_dm else pkt_channel
            store_message(db_conn, packet_id, store_channel, sender, text, received_at)
            if bot_state is not None and pkt_channel == log_channel:
                bot_state["last_message"] = {
                    "channel": pkt_channel,
                    "sender_id": sender,
                    "text": text,
                    "received_at": received_at,
                }

        if reply_fn is None:
            return

        ctx = {
            "interface": interface,
            "sender": sender,
            "db_conn": db_conn,
            "log_channel": log_channel,
        }
        cmd = text.split()[0].lower()
        handler = COMMANDS.get(cmd)
        if handler:
            handler(text, reply_fn, ctx)

    return on_receive


def weather_alert_loop(interface, channel: int, county: str, interval_seconds: int):
    """Background thread: checks for lightning and wind alerts and broadcasts new ones."""
    sent_lightning_ids: set[str] = set()
    sent_wind_ids: set[str] = set()

    def check_and_send():
        lightning_alerts = get_lightning_alerts(county)
        for alert in lightning_alerts:
            if alert["id"] not in sent_lightning_ids:
                msg = format_alert_message(alert)
                log.info(f"Sending lightning alert to ch{channel}: {msg}")
                interface.sendText(msg, channelIndex=channel)
                sent_lightning_ids.add(alert["id"])
        sent_lightning_ids.intersection_update({a["id"] for a in lightning_alerts})

        wind_alerts = get_wind_alerts(county)
        for alert in wind_alerts:
            if alert["id"] not in sent_wind_ids:
                msg = format_wind_alert_message(alert)
                log.info(f"Sending wind alert to ch{channel}: {msg}")
                interface.sendText(msg, channelIndex=channel)
                sent_wind_ids.add(alert["id"])
        sent_wind_ids.intersection_update({a["id"] for a in wind_alerts})

    log.info(f"Weather alert task started (county={county}, interval={interval_seconds}s).")
    check_and_send()
    while True:
        time.sleep(interval_seconds)
        check_and_send()


def db_purge_loop(conn, retain_days: int = 365):
    """Background thread: purges messages older than *retain_days* once per day."""
    PURGE_INTERVAL = 86400  # 24 hours
    log.info(f"DB purge task started (retain={retain_days} days, interval=24h).")
    purge_old_messages(conn, retain_days)
    while True:
        time.sleep(PURGE_INTERVAL)
        purge_old_messages(conn, retain_days)


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
        retain_days = int(msg_log_cfg.get("retain_days", 365))
        db_conn = init_db(db_path)
        threading.Thread(
            target=db_purge_loop,
            args=(db_conn, retain_days),
            daemon=True,
        ).start()

    weather_cfg = cfg.get("weather", {})
    county = str(weather_cfg.get("county", "")) if weather_cfg.get("enabled", True) else ""

    bot_state: dict = {
        "start_time": datetime.now(timezone.utc),
        "channel": channel,
        "log_channel": log_channel,
        "county": county,
        "last_message": None,
    }

    handler = make_receive_handler(interface, channel, db_conn=db_conn, log_channel=log_channel, bot_state=bot_state)

    if weather_cfg.get("enabled", True):
        interval = weather_cfg.get("interval_seconds", 3600)
        threading.Thread(
            target=weather_alert_loop,
            args=(interface, channel, county, interval),
            daemon=True,
        ).start()

    web_cfg = cfg.get("web", {})
    if web_cfg.get("enabled", False):
        web_port = int(web_cfg.get("port", 8080))
        start_web_server(db_conn, bot_state, port=web_port)

    if args.dummy:
        run_dummy_loop(handler, channel, log_channel=log_channel)
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
