"""
MeshtasticBot — listens on a configured channel and replies to text messages.
Also runs background tasks for weather alerts and database maintenance.

Configuration is loaded from config.yaml. See config.yaml for available options.
"""

import argparse
import os
import signal
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

import meshtastic.ble_interface
import meshtastic.serial_interface
import meshtastic.tcp_interface
import structlog
import yaml
from pubsub import pub

from commands import COMMANDS, PRIVILEGED_COMMANDS
from context import BotContext
from db import (
    init_db,
    is_banned,
    is_privileged,
    log_command,
    purge_old_messages,
    store_message,
    upsert_node,
)
from dummy import DummyInterface, run_dummy_loop
from log_config import configure_logging
from weather import (
    format_alert_message,
    format_wind_alert_message,
    get_lightning_alerts,
    get_wind_alerts,
)
from web import push_event, start_web_server

configure_logging()
log = structlog.get_logger()


def send_text_with_retry(interface, text: str, max_attempts: int = 5, base_delay: float = 0.5, **kwargs) -> None:
    """Send *text* via *interface*, retrying up to *max_attempts* times on MeshInterfaceError.

    Uses exponential backoff starting at *base_delay* seconds.
    All extra *kwargs* are forwarded to interface.sendText().
    """
    from meshtastic.mesh_interface import MeshInterface
    delay = base_delay
    for attempt in range(1, max_attempts + 1):
        try:
            interface.sendText(text, **kwargs)
            return
        except MeshInterface.MeshInterfaceError as exc:
            if attempt == max_attempts:
                log.error("send_text_failed", attempts=max_attempts, error=str(exc))
                return
            log.warning(
                "send_text_retry",
                attempt=attempt, max_attempts=max_attempts,
                error=str(exc), retry_delay=round(delay, 1),
            )
            time.sleep(delay)
            delay *= 2

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
    "/addpriv":        1,
    "/removepriv":     1,
    "/awning":         1,
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
            log.info("config_env_override", env_var=env_var)
        except (ValueError, TypeError) as exc:
            log.warning("config_env_override_invalid", env_var=env_var, value=raw, error=str(exc))
    return cfg


def validate_config(cfg: dict) -> None:
    """Raise ValueError with a clear message if required config fields are missing or invalid."""
    import re
    errors = []

    conn = cfg.get("connection", {})
    kind = conn.get("type", "serial")
    if kind not in ("serial", "tcp", "ble"):
        errors.append(f"connection.type must be 'serial', 'tcp', or 'ble' — got '{kind}'")
    if kind == "tcp" and not conn.get("host"):
        errors.append("connection.host is required when connection.type is 'tcp'")

    weather_cfg = cfg.get("weather", {})
    if weather_cfg.get("enabled", True):
        county = str(weather_cfg.get("county", ""))
        if not county:
            errors.append("weather.county is required when weather.enabled is true")
        elif not re.fullmatch(r"\d{2}", county):
            errors.append(
                f"weather.county must be a 2-digit Norwegian fylkesnummer — got '{county}'"
            )

    msg_log_cfg = cfg.get("message_log", {})
    if "retain_days" in msg_log_cfg:
        retain_days = msg_log_cfg["retain_days"]
        if int(retain_days) <= 0:
            errors.append(f"message_log.retain_days must be > 0 — got {retain_days}")

    web_cfg = cfg.get("web", {})
    if "port" in web_cfg:
        port = int(web_cfg["port"])
        if not (1 <= port <= 65535):
            errors.append(f"web.port must be in range 1–65535 — got {port}")

    rl_cfg = cfg.get("rate_limit", {})
    if "bucket_size" in rl_cfg:
        bucket_size = float(rl_cfg["bucket_size"])
        if bucket_size <= 0:
            errors.append(f"rate_limit.bucket_size must be > 0 — got {bucket_size}")
    if "refill_rate" in rl_cfg:
        refill_rate = float(rl_cfg["refill_rate"])
        if refill_rate <= 0:
            errors.append(f"rate_limit.refill_rate must be > 0 — got {refill_rate}")

    if errors:
        raise ValueError("Invalid config.yaml:\n" + "\n".join(f"  - {e}" for e in errors))


def connect(cfg: dict):
    """Create and return a Meshtastic interface based on config."""
    conn = cfg.get("connection", {})
    kind = conn.get("type", "serial")

    if kind == "serial":
        port = conn.get("port")
        log.info("connecting", transport="serial", port=port or "auto")
        return meshtastic.serial_interface.SerialInterface(devPath=port)

    if kind == "tcp":
        host = conn["host"]
        log.info("connecting", transport="tcp", host=host)
        return meshtastic.tcp_interface.TCPInterface(hostname=host)

    if kind == "ble":
        address = conn.get("address")
        log.info("connecting", transport="ble", address=address or "auto")
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
            log.error("connection_failed", attempt=attempt + 1, error=str(exc), retry_delay_s=round(delay))
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
    flipper_cfg: dict | None = None,
):
    # Token bucket state: sender → [tokens, last_refill_timestamp]
    _buckets: dict[str, list] = {}
    # Senders who have already received a rate-limit warning (cleared on next success)
    _warned: set[str] = set()
    # Recently seen packet IDs — prevents duplicate processing when the same
    # packet is relayed by multiple mesh nodes (capped to avoid unbounded growth)
    _seen_ids: set[str] = set()
    _SEEN_IDS_MAX = 500

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

        # Deduplicate by packet ID — same packet may arrive via multiple relay hops
        raw_pkt_id = packet.get("id")
        if raw_pkt_id is not None:
            pkt_key = str(raw_pkt_id)
            if pkt_key in _seen_ids:
                log.debug("packet_duplicate_skipped", packet_id=pkt_key)
                return
            if len(_seen_ids) >= _SEEN_IDS_MAX:
                _seen_ids.clear()
            _seen_ids.add(pkt_key)

        sender = packet.get("fromId", "unknown")
        to_id = packet.get("toId", "^all")
        is_dm = to_id != "^all"
        pkt_channel = packet.get("channel", 0)

        if is_dm:
            log.info("message_received", direction="dm", sender=sender, text=text)
            def reply_fn(msg, _to=sender):
                log.info("message_sent", direction="dm", to=_to, text=msg)
                send_text_with_retry(interface, msg, destinationId=_to, channelIndex=0)
        elif pkt_channel == channel:
            log.info("message_received", direction="channel", channel=channel, sender=sender, text=text)
            def reply_fn(msg, _ch=channel, _to=sender):
                log.info("message_sent", direction="channel", channel=_ch, to=_to, text=msg)
                send_text_with_retry(interface, msg, channelIndex=_ch)
        else:
            reply_fn = None

        # Store every received message. DMs are stored with channel = -1.
        node_info = (interface.nodes or {}).get(sender, {})
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
            push_event("message", {
                "channel": store_channel,
                "sender_id": sender,
                "text": text,
                "received_at": received_at,
            })

            node_data = {
                "node_id": sender,
                "long_name": node_info.get("user", {}).get("longName"),
                "short_name": node_info.get("user", {}).get("shortName"),
                "last_seen": received_at,
                "last_snr": packet.get("rxSnr"),
                "last_rssi": packet.get("rxRssi"),
                "lat": node_info.get("position", {}).get("latitude"),
                "lon": node_info.get("position", {}).get("longitude"),
                "public_key": node_info.get("user", {}).get("publicKey"),
            }
            upsert_node(
                db_conn,
                node_id=node_data["node_id"],
                long_name=node_data["long_name"],
                short_name=node_data["short_name"],
                last_seen=node_data["last_seen"],
                snr=node_data["last_snr"],
                rssi=node_data["last_rssi"],
                lat=node_data["lat"],
                lon=node_data["lon"],
                public_key=node_data["public_key"],
            )
            push_event("node_update", node_data)

        if reply_fn is None:
            return

        cmd = text.split()[0].lower()
        handler = COMMANDS.get(cmd)
        if not handler:
            return

        # Check ban before anything else — silently ignore and log
        if db_conn is not None and is_banned(db_conn, sender):
            log.info("command_blocked", reason="banned", sender=sender, cmd=cmd)
            log_command(db_conn, sender, cmd, "banned")
            push_event("audit_update", {"node_id": sender, "command": cmd, "status": "banned"})
            return

        # Check privilege for restricted commands
        if cmd in PRIVILEGED_COMMANDS:
            sender_key = node_info.get("user", {}).get("publicKey") if db_conn is not None else None
            if db_conn is None or not is_privileged(db_conn, sender, sender_key):
                log.info("command_blocked", reason="not_privileged", sender=sender, cmd=cmd)
                if db_conn is not None:
                    log_command(db_conn, sender, cmd, "not_privileged")
                    push_event("audit_update", {"node_id": sender, "command": cmd, "status": "not_privileged"})
                return

        cost = COMMAND_COSTS.get(cmd, 1)
        bucket = _get_tokens(sender)
        if bucket[0] < cost:
            log.info(
                "command_blocked", reason="rate_limited",
                sender=sender, cmd=cmd,
                tokens_have=round(bucket[0], 1), tokens_need=cost,
            )
            if db_conn is not None:
                log_command(db_conn, sender, cmd, "rate_limited")
                push_event("audit_update", {"node_id": sender, "command": cmd, "status": "rate_limited"})
            if sender not in _warned:
                _warned.add(sender)
                reply_fn("⛔ For mange kommandoer på kort tid. Vent litt og prøv igjen.")
            return
        bucket[0] -= cost
        _warned.discard(sender)

        if db_conn is not None:
            log_command(db_conn, sender, cmd, "ok")
            push_event("audit_update", {"node_id": sender, "command": cmd, "status": "ok"})

        ctx: BotContext = {
            "interface": interface,
            "sender": sender,
            "db_conn": db_conn,
            "log_channel": log_channel,
            "start_time": bot_state["start_time"] if bot_state else None,
            "county": bot_state["county"] if bot_state else None,
            "flipper_cfg": flipper_cfg,
        }
        handler(text, reply_fn, ctx)

    return on_receive


def _make_signal_handler(shutdown_event: threading.Event):
    """Return a signal handler that sets *shutdown_event*."""
    def handler(signum, frame):
        log.info("signal_received", signum=signum)
        shutdown_event.set()
    return handler


def _make_sighup_handler(config_path: str, bot_state: dict):
    """Return a SIGHUP handler that reloads config and updates *bot_state* in-place.

    Updates: county, bucket_size, refill_rate, admin_username, admin_password.
    If the reloaded config fails validation the existing values are preserved.
    """
    def handler(signum, frame):
        log.info("sighup_received")
        try:
            cfg = load_config(config_path)
            validate_config(cfg)
        except FileNotFoundError:
            log.error("config_reload_failed", reason="file_not_found", path=config_path)
            return
        except ValueError as exc:
            log.error("config_reload_failed", reason="invalid_config", error=str(exc))
            return
        except Exception as exc:
            log.error("config_reload_failed", error=str(exc))
            return

        weather_cfg = cfg.get("weather", {})
        bot_state["county"] = (
            str(weather_cfg.get("county", ""))
            if weather_cfg.get("enabled", True)
            else ""
        )
        rl_cfg = cfg.get("rate_limit", {})
        bot_state["bucket_size"] = float(rl_cfg.get("bucket_size", bot_state.get("bucket_size", 5.0)))
        bot_state["refill_rate"] = float(rl_cfg.get("refill_rate", bot_state.get("refill_rate", 0.1)))
        admin_cfg = cfg.get("admin", {})
        bot_state["admin_username"] = str(admin_cfg.get("username", ""))
        bot_state["admin_password"] = str(admin_cfg.get("password", ""))
        log.info(
            "config_reloaded",
            county=bot_state["county"],
            bucket_size=bot_state["bucket_size"],
            refill_rate=bot_state["refill_rate"],
        )
    return handler


def weather_alert_loop(
    interface, channel: int, county: str, interval_seconds: int,
    shutdown_event: threading.Event | None = None,
):
    """Background thread: checks for lightning and wind alerts and broadcasts new ones."""
    if shutdown_event is None:
        shutdown_event = threading.Event()
    sent_lightning_ids: set[str] = set()
    sent_wind_ids: set[str] = set()

    def check_and_send():
        lightning_alerts = get_lightning_alerts(county)
        for alert in lightning_alerts:
            if alert["id"] not in sent_lightning_ids:
                pages = format_alert_message(alert)
                log.info("weather_alert_sent", kind="lightning", channel=channel, alert_id=alert["id"])
                for i, page in enumerate(pages):
                    if i > 0:
                        time.sleep(3)
                    send_text_with_retry(interface, page, channelIndex=channel)
                sent_lightning_ids.add(alert["id"])
        sent_lightning_ids.intersection_update({a["id"] for a in lightning_alerts})

        wind_alerts = get_wind_alerts(county)
        for alert in wind_alerts:
            if alert["id"] not in sent_wind_ids:
                pages = format_wind_alert_message(alert)
                log.info("weather_alert_sent", kind="wind", channel=channel, alert_id=alert["id"])
                for i, page in enumerate(pages):
                    if i > 0:
                        time.sleep(3)
                    send_text_with_retry(interface, page, channelIndex=channel)
                sent_wind_ids.add(alert["id"])
        sent_wind_ids.intersection_update({a["id"] for a in wind_alerts})

    log.info("weather_alert_task_started", county=county, interval_s=interval_seconds)
    check_and_send()
    while not shutdown_event.wait(timeout=interval_seconds):
        check_and_send()


def db_purge_loop(
    conn, retain_days: int = 365,
    shutdown_event: threading.Event | None = None,
    interval_seconds: int = 86400,
):
    """Background thread: purges messages older than *retain_days* once per day."""
    if shutdown_event is None:
        shutdown_event = threading.Event()
    log.info("db_purge_task_started", retain_days=retain_days, interval_s=interval_seconds)
    purge_old_messages(conn, retain_days)
    while not shutdown_event.wait(timeout=interval_seconds):
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


def node_sync_loop(
    interface, db_conn,
    shutdown_event: threading.Event | None = None,
    interval_seconds: int = 300,
):
    """Background thread: periodically syncs interface.nodes → DB."""
    if shutdown_event is None:
        shutdown_event = threading.Event()
    log.info("node_sync_task_started", interval_s=interval_seconds)
    while not shutdown_event.wait(timeout=interval_seconds):
        try:
            n = sync_nodes_from_interface(interface, db_conn)
            log.debug("node_sync_complete", nodes_upserted=n)
        except Exception as exc:
            log.warning("node_sync_failed", error=str(exc))


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
        log.error("config_invalid", error=str(exc))
        raise SystemExit(1)
    channel = cfg.get("channel", 2)
    if args.channel is not None:
        channel = args.channel

    shutdown_event = threading.Event()
    signal.signal(signal.SIGTERM, _make_signal_handler(shutdown_event))
    signal.signal(signal.SIGINT, _make_signal_handler(shutdown_event))

    if args.dummy:
        interface = DummyInterface()
        log.info("dummy_mode_active")
    else:
        interface = connect_with_retry(cfg)

    msg_log_cfg = cfg.get("message_log", {})
    db_conn = None
    log_channel = None
    background_threads = []
    if msg_log_cfg.get("enabled", False):
        log_channel = int(msg_log_cfg.get("channel", 1))
        db_path = msg_log_cfg.get("db_path", "messages.db")
        retain_days = int(msg_log_cfg.get("retain_days", 365))
        db_conn = init_db(db_path)
        background_threads.append(threading.Thread(
            target=db_purge_loop,
            args=(db_conn, retain_days, shutdown_event),
            daemon=True,
        ))
        # Populate the node registry from what the interface already knows.
        n = sync_nodes_from_interface(interface, db_conn)
        log.info("initial_node_sync", nodes=n)
        background_threads.append(threading.Thread(
            target=node_sync_loop,
            args=(interface, db_conn, shutdown_event),
            daemon=True,
        ))

    weather_cfg = cfg.get("weather", {})
    county = str(weather_cfg.get("county", "")) if weather_cfg.get("enabled", True) else ""

    rl_cfg = cfg.get("rate_limit", {})
    bot_state: dict = {
        "start_time": datetime.now(timezone.utc),
        "channel": channel,
        "log_channel": log_channel,
        "county": county,
        "last_message": None,
        "bucket_size": float(rl_cfg.get("bucket_size", 5.0)),
        "refill_rate": float(rl_cfg.get("refill_rate", 0.1)),
        "admin_username": str(cfg.get("admin", {}).get("username", "")),
        "admin_password": str(cfg.get("admin", {}).get("password", "")),
        "connected": not args.dummy,
        # The interface is stored so the web UI can send messages directly.
        # Updated in-place on reconnect so the web UI always uses the live interface.
        "interface": interface,
        "send_fn": send_text_with_retry,
    }

    signal.signal(signal.SIGHUP, _make_sighup_handler(CONFIG_FILE, bot_state))

    bucket_size = float(rl_cfg.get("bucket_size", 5.0))
    refill_rate = float(rl_cfg.get("refill_rate", 0.1))  # tokens/second

    flipper_raw = cfg.get("flipper", {})
    flipper_cfg = flipper_raw if flipper_raw.get("device") else None
    if flipper_cfg:
        log.info("flipper_configured", device=flipper_cfg["device"])

    handler = make_receive_handler(
        interface, channel,
        db_conn=db_conn,
        log_channel=log_channel,
        bot_state=bot_state,
        bucket_size=bucket_size,
        refill_rate=refill_rate,
        flipper_cfg=flipper_cfg,
    )

    if weather_cfg.get("enabled", True):
        interval = weather_cfg.get("interval_seconds", 3600)
        background_threads.append(threading.Thread(
            target=weather_alert_loop,
            args=(interface, channel, county, interval, shutdown_event),
            daemon=True,
        ))

    for t in background_threads:
        t.start()

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
        log.info("bot_ready", channel=channel)
        try:
            while not shutdown_event.is_set():
                shutdown_event.wait(timeout=1)
                # Reconnect if the interface has lost connection
                if getattr(interface, "isConnected", None) is not None and not interface.isConnected:
                    log.warning("device_disconnected")
                    try:
                        pub.unsubscribe(handler, "meshtastic.receive.text")
                    except Exception:
                        pass
                    try:
                        interface.close()
                    except Exception:
                        pass
                    interface = connect_with_retry(cfg)
                    bot_state["interface"] = interface
                    pub.subscribe(handler, "meshtastic.receive.text")
                    log.info("device_reconnected")
        finally:
            log.info("shutdown_started")
            shutdown_event.set()
            for t in background_threads:
                t.join(timeout=5)
            interface.close()
            log.info("shutdown_complete")


if __name__ == "__main__":
    main()
