"""
MeshtasticBot — listens on a configured channel and replies to text messages.
Also runs background tasks for weather alerts and database maintenance.

Configuration is loaded from config.yaml. See config.yaml for available options.
"""

import argparse
import logging
import os
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
from db import init_db, is_banned, log_command, purge_old_messages, store_message, upsert_node
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

# Token cost per command — higher cost = more messages generated = fewer bursts allowed.
COMMAND_COSTS: dict[str, int] = {
    "/ping":           1,
    "/help":           1,
    "/whois":          1,
    "/nodes":          2,
    "/radio":          2,
    "/alert":          2,
    "/calling":        2,
    "/mvhf":           2,
    "/weather":        3,
    "/24hour":         3,
    "/24h":            3,
    "/bandplan":       3,
    "/bandplan_check": 3,
    "/krslog":         3,
    "/krslast":        3,
}

CONFIG_FILE = "config.yaml"
_ENV_PREFIX = "MESHTASTIC__"


def _set_nested(cfg: dict, keys: list[str], value) -> None:
    """Set a deeply nested key in *cfg* given a list of *keys*."""
    for key in keys[:-1]:
        cfg = cfg.setdefault(key, {})
    cfg[keys[-1]] = value


def _get_nested(cfg: dict, keys: list[str]):
    """Return the existing value at *keys* path, or None if not found."""
    node = cfg
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _coerce(raw: str, kind: type):
    """Convert *raw* string to *kind*. Booleans accept 1/true/yes/on."""
    if kind is bool:
        return raw.lower() in ("1", "true", "yes", "on")
    return kind(raw)


def load_config(path: str) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    for env_var, raw in os.environ.items():
        if not env_var.startswith(_ENV_PREFIX):
            continue
        keys = env_var[len(_ENV_PREFIX):].lower().split("__")
        existing = _get_nested(cfg, keys)
        kind = type(existing) if existing is not None else str
        try:
            _set_nested(cfg, keys, _coerce(raw, kind))
            log.info(f"Config override from env: {env_var}")
        except (ValueError, TypeError) as exc:
            log.warning(f"Ignoring invalid env var {env_var}={raw!r}: {exc}")
    return cfg


def validate_config(cfg: dict) -> None:
    """Raise ValueError with a clear message if required config fields are missing or invalid."""
    errors = []

    conn = cfg.get("connection", {})
    kind = conn.get("type", "serial")
    if kind not in ("serial", "tcp", "ble"):
        errors.append(f"connection.type must be 'serial', 'tcp', or 'ble' — got '{kind}'")
    if kind == "tcp" and not conn.get("host"):
        errors.append("connection.host is required when connection.type is 'tcp'")

    weather_cfg = cfg.get("weather", {})
    if weather_cfg.get("enabled", True) and not weather_cfg.get("county"):
        errors.append("weather.county is required when weather.enabled is true")

    if errors:
        raise ValueError("Invalid config.yaml:\n" + "\n".join(f"  - {e}" for e in errors))


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


def connect_with_retry(cfg: dict, base_delay: float = 5.0, max_delay: float = 300.0):
    """Attempt to connect, retrying with exponential backoff on failure.

    Retries indefinitely — the bot should always reconnect rather than die.
    base_delay: initial wait in seconds before first retry.
    max_delay: upper cap on wait between retries.
    """
    attempt = 0
    while True:
        try:
            return connect(cfg)
        except Exception as exc:
            delay = min(base_delay * (2 ** attempt), max_delay)
            log.error(f"Connection failed (attempt {attempt + 1}): {exc}. Retrying in {delay:.0f}s…")
            time.sleep(delay)
            attempt += 1


def make_receive_handler(
    interface,
    channel: int,
    db_conn=None,
    log_channel: int | None = None,
    bot_state: dict | None = None,
    rate_limit_seconds: int = 10,  # kept for backwards compat; ignored when bucket params set
    bucket_size: float = 5.0,
    refill_rate: float = 0.1,  # tokens per second (default: 1 token / 10 s)
):
    # Token bucket state: sender → [tokens, last_refill_timestamp]
    _buckets: dict[str, list] = {}
    # Senders who have already received a rate-limit warning (cleared on next success)
    _warned: set[str] = set()

    def _get_tokens(sender: str) -> list:
        if sender not in _buckets:
            _buckets[sender] = [bucket_size, time.time()]
        bucket = _buckets[sender]
        now = time.time()
        elapsed = now - bucket[1]
        bucket[0] = min(bucket_size, bucket[0] + elapsed * refill_rate)
        bucket[1] = now
        return bucket

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

            node_info = (interface.nodes or {}).get(sender, {})
            upsert_node(
                db_conn,
                node_id=sender,
                long_name=node_info.get("user", {}).get("longName"),
                short_name=node_info.get("user", {}).get("shortName"),
                last_seen=received_at,
                snr=packet.get("rxSnr"),
                rssi=packet.get("rxRssi"),
                lat=node_info.get("position", {}).get("latitude"),
                lon=node_info.get("position", {}).get("longitude"),
            )

        if reply_fn is None:
            return

        cmd = text.split()[0].lower()
        handler = COMMANDS.get(cmd)
        if not handler:
            return

        # Check ban before anything else — silently ignore and log
        if db_conn is not None and is_banned(db_conn, sender):
            log.info(f"Banned node {sender} attempted {cmd} — ignoring.")
            log_command(db_conn, sender, cmd, "banned")
            return

        cost = COMMAND_COSTS.get(cmd, 1)
        bucket = _get_tokens(sender)
        if bucket[0] < cost:
            log.info(f"Rate limit: dropping {cmd} from {sender} (need {cost} tokens, have {bucket[0]:.1f})")
            if db_conn is not None:
                log_command(db_conn, sender, cmd, "rate_limited")
            if sender not in _warned:
                _warned.add(sender)
                reply_fn("⛔ For mange kommandoer på kort tid. Vent litt og prøv igjen.")
            return
        bucket[0] -= cost
        _warned.discard(sender)

        if db_conn is not None:
            log_command(db_conn, sender, cmd, "ok")

        ctx = {
            "interface": interface,
            "sender": sender,
            "db_conn": db_conn,
            "log_channel": log_channel,
            "start_time": bot_state["start_time"] if bot_state else None,
            "county": bot_state["county"] if bot_state else None,
        }
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


def sync_nodes_from_interface(interface, db_conn) -> int:
    """Upsert all nodes currently known to the interface into the nodes DB table.

    Returns the number of nodes synced.
    """
    nodes = interface.nodes or {}
    now = datetime.now(timezone.utc).isoformat()
    for node_id, info in nodes.items():
        user = info.get("user", {})
        pos = info.get("position", {})
        upsert_node(
            db_conn,
            node_id=node_id,
            long_name=user.get("longName"),
            short_name=user.get("shortName"),
            snr=info.get("snr"),
            lat=pos.get("latitude"),
            lon=pos.get("longitude"),
            last_seen=now,
        )
    return len(nodes)


def node_sync_loop(interface, db_conn, interval_seconds: int = 300):
    """Background thread: periodically syncs interface.nodes → DB."""
    log.info(f"Node sync task started (interval={interval_seconds}s).")
    while True:
        time.sleep(interval_seconds)
        try:
            n = sync_nodes_from_interface(interface, db_conn)
            log.debug(f"Node sync: {n} nodes upserted.")
        except Exception as exc:
            log.warning(f"Node sync failed: {exc}")


def main():
    parser = argparse.ArgumentParser(description="MeshtasticBot")
    parser.add_argument("--dummy", action="store_true",
                        help="Run in dummy mode (no device required — interactive CLI)")
    parser.add_argument("--channel", type=int, default=None,
                        help="Override the channel index from config.yaml (dummy mode only)")
    args = parser.parse_args()

    cfg = load_config(CONFIG_FILE)
    try:
        validate_config(cfg)
    except ValueError as exc:
        log.error(str(exc))
        raise SystemExit(1)
    channel = cfg.get("channel", 2)
    if args.channel is not None:
        channel = args.channel

    if args.dummy:
        interface = DummyInterface()
        log.info("Dummy mode active — no device connection.")
    else:
        interface = connect_with_retry(cfg)

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
        # Populate the node registry from what the interface already knows.
        n = sync_nodes_from_interface(interface, db_conn)
        log.info(f"Initial node sync: {n} nodes loaded into registry.")
        threading.Thread(
            target=node_sync_loop,
            args=(interface, db_conn),
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

    rl_cfg = cfg.get("rate_limit", {})
    bucket_size = float(rl_cfg.get("bucket_size", 5.0))
    refill_rate = float(rl_cfg.get("refill_rate", 0.1))  # tokens/second
    handler = make_receive_handler(
        interface, channel,
        db_conn=db_conn,
        log_channel=log_channel,
        bot_state=bot_state,
        bucket_size=bucket_size,
        refill_rate=refill_rate,
    )

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
        admin_cfg = cfg.get("admin", {})
        start_web_server(
            db_conn, bot_state, port=web_port,
            admin_username=str(admin_cfg.get("username", "")),
            admin_password=str(admin_cfg.get("password", "")),
        )

    if args.dummy:
        run_dummy_loop(handler, channel, log_channel=log_channel)
        interface.close()
    else:
        pub.subscribe(handler, "meshtastic.receive.text")
        log.info(f"Bot ready — listening on channel {channel}. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
                # Reconnect if the interface has lost connection
                if getattr(interface, "isConnected", None) is not None and not interface.isConnected:
                    log.warning("Device disconnected — reconnecting…")
                    try:
                        pub.unsubscribe(handler, "meshtastic.receive.text")
                    except Exception:
                        pass
                    try:
                        interface.close()
                    except Exception:
                        pass
                    interface = connect_with_retry(cfg)
                    pub.subscribe(handler, "meshtastic.receive.text")
                    log.info("Reconnected successfully.")
        except KeyboardInterrupt:
            log.info("Shutting down.")
        finally:
            interface.close()


if __name__ == "__main__":
    main()
