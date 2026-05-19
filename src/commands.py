"""
Command handlers for MeshtasticBot.

Every handler has the uniform signature:
    handler(text: str, reply_fn: callable, ctx: BotContext) -> None

Commands are defined once in COMMAND_REGISTRY — dispatch (COMMANDS),
privilege gating (PRIVILEGED_COMMANDS), and /help pages are all derived
from that single source of truth.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bandplan import (
    BANDPLAN,
    CALLING_FREQUENCIES,
    format_bandplan_messages,
    format_calling_messages,
    lookup_frequency,
    parse_frequency_mhz,
    resolve_band,
)
from constants import MAX_KRSLAST, MAX_KRSLOG_HOURS, PACK_BYTES
from context import BotContext
from db import (
    add_privileged_node,
    get_last_messages,
    get_node,
    get_recent_messages,
    is_privileged,
    lookup_nodes_by_name,
    remove_privileged_node,
)
from marine import format_mvhf_channel, format_mvhf_list_messages
from radio import format_radio_messages, get_radio_forecast
from weather import (
    format_alert_message,
    format_forecast_24h_messages,
    format_forecast_messages,
    format_wind_alert_message,
    get_forecast,
    get_forecast_24h,
    get_lightning_alerts,
    get_node_position,
    get_wind_alerts,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Command descriptor
# ---------------------------------------------------------------------------

HELP_COMMANDS_PER_PAGE = 5

HELP_FOOTER = (
    "- Kommandoer funker via DM\n"
    "- GPS må deles for værvarsler\n"
    "- Lynnvarsler og vindvarsler sendes automatisk"
)


@dataclass
class Command:
    """Descriptor for a single bot command."""

    name: str
    handler: callable
    description: str
    privileged: bool = False
    aliases: list[str] = field(default_factory=list)


def build_help_pages(privileged: bool = False) -> list[str]:
    """Build /help pages from the registry. Privileged commands only shown when privileged=True."""
    entries = [c for c in COMMAND_REGISTRY if not c.privileged or privileged]
    lines = []
    for c in entries:
        names = "|".join([c.name] + c.aliases)
        lines.append(f"{names} - {c.description}")

    chunks = [lines[i:i + HELP_COMMANDS_PER_PAGE] for i in range(0, len(lines), HELP_COMMANDS_PER_PAGE)]
    total = len(chunks) + 1  # +1 for the info/footer page
    pages = [f"Kommandoer [{i+1}/{total}]:\n" + "\n".join(chunk) for i, chunk in enumerate(chunks)]
    pages.append(f"Info [{total}/{total}]:\n{HELP_FOOTER}")
    return pages


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _send_pages(reply_fn, pages: list[str]) -> None:
    """Send pages with [N/total] counters, sleeping 3 s between each."""
    total = len(pages)
    for i, page in enumerate(pages):
        if i > 0:
            time.sleep(3)
        reply_fn(f"[{i+1}/{total}] {page}" if total > 1 else page)


def _build_log_pages(rows: list[dict], header: str) -> list[str]:
    """Pack log row dicts into byte-safe pages under PACK_BYTES."""
    pages: list[str] = []
    current_lines: list[str] = []
    include_header = True

    for r in rows:
        ts = r["received_at"][11:16]  # HH:MM from ISO timestamp
        line = f"{ts} {r['sender_id']}: {r['text']}"
        candidate = (header + "\n" + "\n".join(current_lines + [line])
                     if include_header else "\n".join(current_lines + [line]))
        if current_lines and len(candidate.encode("utf-8")) > PACK_BYTES:
            pages.append(header + "\n" + "\n".join(current_lines)
                         if include_header else "\n".join(current_lines))
            current_lines = [line]
            include_header = False
        else:
            current_lines.append(line)

    if current_lines:
        pages.append(header + "\n" + "\n".join(current_lines)
                     if include_header else "\n".join(current_lines))

    return pages


# ---------------------------------------------------------------------------
# Command handlers  —  signature: (text, reply_fn, ctx)
# ---------------------------------------------------------------------------

def handle_ping_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Reply with uptime and number of nodes currently seen on the mesh."""
    start_time = ctx.get("start_time")
    if start_time:
        delta = datetime.now(timezone.utc) - start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        uptime = f"{hours}t {minutes}m" if hours else f"{minutes}m"
    else:
        uptime = "ukjent"

    nodes = ctx["interface"].nodes or {}
    reply_fn(f"🟢 Pong! Oppe: {uptime} | Noder sett: {len(nodes)}")


def handle_nodes_command(text: str, reply_fn, ctx: BotContext) -> None:
    """List mesh nodes currently seen by the interface with SNR."""
    nodes: dict = ctx["interface"].nodes or {}
    if not nodes:
        reply_fn("Ingen noder sett ennå.")
        return

    lines = []
    for node_id, info in nodes.items():
        name = (info.get("user", {}).get("longName")
                or info.get("user", {}).get("shortName")
                or node_id)
        snr = info.get("snr")
        snr_str = f" SNR:{snr:.1f}" if snr is not None else ""
        lines.append(f"{node_id} {name}{snr_str}")

    header = f"Noder ({len(nodes)}):"
    pages: list[str] = []
    current: list[str] = []
    use_header = True
    for line in lines:
        block = (header + "\n" + "\n".join(current + [line])) if use_header else "\n".join(current + [line])
        if current and len(block.encode("utf-8")) > PACK_BYTES:
            pages.append((header + "\n" + "\n".join(current)) if use_header else "\n".join(current))
            current = [line]
            use_header = False
        else:
            current.append(line)
    if current:
        pages.append((header + "\n" + "\n".join(current)) if use_header else "\n".join(current))

    _send_pages(reply_fn, pages)


def handle_alert_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Fetch active lightning and wind alerts on demand and send them as replies."""
    county = ctx.get("county")
    if not county:
        reply_fn("Varseltjenesten er ikke konfigurert (mangler county i config).")
        return

    lightning = get_lightning_alerts(county)
    wind = get_wind_alerts(county)
    all_alerts = [(a, "lightning") for a in lightning] + [(a, "wind") for a in wind]

    if not all_alerts:
        reply_fn("✅ Ingen aktive varsler for ditt område.")
        return

    reply_fn(f"⚠️ Aktive varsler ({len(all_alerts)}):")
    time.sleep(2)
    pages = []
    for alert, kind in all_alerts:
        if kind == "lightning":
            pages.append(format_alert_message(alert))
        else:
            pages.append(format_wind_alert_message(alert))
    _send_pages(reply_fn, pages)


def handle_help_command(text: str, reply_fn, ctx: BotContext) -> None:
    db_conn = ctx.get("db_conn")
    sender = ctx.get("sender")
    priv = db_conn is not None and sender is not None and is_privileged(db_conn, sender)
    pages = build_help_pages(privileged=priv)
    for i, page in enumerate(pages):
        if i > 0:
            time.sleep(2)
        reply_fn(page)


def handle_weather_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Look up sender position, fetch 7-day forecast, send multi-message reply."""
    interface, sender = ctx["interface"], ctx["sender"]
    pos = get_node_position(interface, sender)
    if pos is None:
        reply_fn("Ingen GPS-posisjon funnet for din node. Del posisjon og prøv igjen.")
        return
    lat, lon = pos
    log.info(f"/weather requested by {sender} at ({lat}, {lon})")
    forecast = get_forecast(lat, lon)
    if forecast is None:
        reply_fn("Klarte ikke hente varsel fra yr.no.")
        return
    _send_pages(reply_fn, format_forecast_messages(forecast, lat, lon))


def handle_24h_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Look up sender position, fetch 24-hour forecast, send multi-message reply."""
    interface, sender = ctx["interface"], ctx["sender"]
    pos = get_node_position(interface, sender)
    if pos is None:
        reply_fn("Ingen GPS-posisjon funnet for din node. Del posisjon og prøv igjen.")
        return
    lat, lon = pos
    log.info(f"/24hour requested by {sender} at ({lat}, {lon})")
    forecast = get_forecast_24h(lat, lon)
    if forecast is None:
        reply_fn("Klarte ikke hente varsel fra yr.no.")
        return
    _send_pages(reply_fn, format_forecast_24h_messages(forecast, lat, lon))


def handle_radio_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Fetch amateur radio band conditions and send as multi-message reply."""
    data = get_radio_forecast()
    if data is None:
        reply_fn("Klarte ikke hente radiokondisjon fra HamQSL.")
        return
    _send_pages(reply_fn, format_radio_messages(data))


def handle_calling_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Parse band from command text and send calling frequencies."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        reply_fn(f"Bruk: /calling <bånd>\nTilgjengelig: {', '.join(CALLING_FREQUENCIES.keys())}")
        return
    band = resolve_band(parts[1])
    if band is None or band not in CALLING_FREQUENCIES:
        reply_fn(f"Ukjent bånd '{parts[1]}'.\nTilgjengelig: {', '.join(CALLING_FREQUENCIES.keys())}")
        return
    log.info(f"/calling {band} requested")
    _send_pages(reply_fn, format_calling_messages(band))


def handle_bandplan_check_command(text: str, reply_fn, ctx: BotContext) -> None:
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


def handle_bandplan_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Parse band from command text and send band plan segments."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        reply_fn(f"Bruk: /bandplan <bånd>\nTilgjengelig: {', '.join(BANDPLAN.keys())}")
        return
    band = resolve_band(parts[1])
    if band is None:
        reply_fn(f"Ukjent bånd '{parts[1]}'.\nTilgjengelig: {', '.join(BANDPLAN.keys())}")
        return
    log.info(f"/bandplan {band} requested")
    _send_pages(reply_fn, format_bandplan_messages(band))


def handle_mvhf_command(text: str, reply_fn, ctx: BotContext) -> None:
    """List key Marine VHF channels, or look up a specific channel."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) >= 2 and parts[1].strip():
        reply_fn(format_mvhf_channel(parts[1].strip()))
        return
    _send_pages(reply_fn, format_mvhf_list_messages(groups=["Nød/DSC", "Havn/trafikk"]))


def handle_whois_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Look up a node by ID or name. /whois !id  or  /whois <name>"""
    db_conn = ctx["db_conn"]
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        reply_fn("Bruk: /whois <node-ID eller navn>\nEks: /whois !aabbccdd  eller  /whois Alpha")
        return
    if db_conn is None:
        reply_fn("Node-registeret er ikke aktivert.")
        return

    query = parts[1].strip()

    if query.startswith("!"):
        node = get_node(db_conn, query)
        nodes = [node] if node else []
    else:
        nodes = lookup_nodes_by_name(db_conn, query)

    if not nodes:
        reply_fn(f"Ingen noder funnet for '{query}'.")
        return

    pages = []
    for n in nodes:
        name = n.get("long_name") or n.get("short_name") or n["node_id"]
        short = f" ({n['short_name']})" if n.get("short_name") else ""
        snr = f" SNR:{n['last_snr']:.1f}" if n.get("last_snr") is not None else ""
        rssi = f" RSSI:{n['last_rssi']}" if n.get("last_rssi") is not None else ""
        ts = n["last_seen"][:16].replace("T", " ") if n.get("last_seen") else "?"
        pos = ""
        if n.get("lat") is not None and n.get("lon") is not None:
            pos = f"\nPos: {n['lat']:.4f},{n['lon']:.4f}"
        pages.append(f"{n['node_id']}\n{name}{short}{snr}{rssi}\nSist sett: {ts}{pos}")

    _send_pages(reply_fn, pages)


def handle_krslog_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Return recent messages from the log channel. Optional arg overrides the hour window."""
    db_conn, log_channel = ctx["db_conn"], ctx["log_channel"]
    parts = text.strip().split(maxsplit=1)
    hours = 24
    if len(parts) >= 2:
        try:
            hours = int(parts[1].strip())
            if hours < 1:
                raise ValueError
        except ValueError:
            reply_fn(f"Bruk: /krslog [antall timer]\nEks: /krslog 48 (maks {MAX_KRSLOG_HOURS}t)")
            return
        if hours > MAX_KRSLOG_HOURS:
            hours = MAX_KRSLOG_HOURS
            reply_fn(f"Maks {MAX_KRSLOG_HOURS}t – viser siste {MAX_KRSLOG_HOURS}t.")

    if db_conn is None:
        reply_fn("Meldingslogg er ikke aktivert.")
        return
    rows = get_recent_messages(db_conn, log_channel, hours)
    if not rows:
        reply_fn(f"Ingen meldinger siste {hours}t.")
        return
    log.info(f"/krslog {hours}h — {len(rows)} message(s)")
    _send_pages(reply_fn, _build_log_pages(rows, f"Logg siste {hours}t:"))


def handle_krslast_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Return the N most recent messages from the log channel. Default 10, max 100."""
    db_conn, log_channel = ctx["db_conn"], ctx["log_channel"]
    parts = text.strip().split(maxsplit=1)
    count = 10
    if len(parts) >= 2:
        try:
            count = int(parts[1].strip())
            if count < 1:
                raise ValueError
        except ValueError:
            reply_fn(f"Bruk: /krslast [antall]\nEks: /krslast 20 (maks {MAX_KRSLAST})")
            return
        if count > MAX_KRSLAST:
            count = MAX_KRSLAST
            reply_fn(f"Maks {MAX_KRSLAST} – viser siste {MAX_KRSLAST} meldinger.")

    if db_conn is None:
        reply_fn("Meldingslogg er ikke aktivert.")
        return
    rows = get_last_messages(db_conn, log_channel, count)
    if not rows:
        reply_fn("Ingen meldinger i loggen.")
        return
    log.info(f"/krslast {count} — {len(rows)} message(s)")
    _send_pages(reply_fn, _build_log_pages(rows, f"Siste {len(rows)} meldinger:"))


def handle_addpriv_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Add a node to the privileged list. Usage: /addpriv <node_id>"""
    db_conn = ctx.get("db_conn")
    sender = ctx.get("sender", "unknown")
    parts = text.split()
    if len(parts) < 2:
        reply_fn("Bruk: /addpriv <node_id>")
        return
    target = parts[1]
    if db_conn is None:
        reply_fn("❌ Ingen database tilgjengelig.")
        return
    node = get_node(db_conn, target)
    pub_key = node.get("public_key") if node else None
    add_privileged_node(db_conn, target, added_by=sender, public_key=pub_key)
    name = (node.get("long_name") or node.get("short_name") or target) if node else target
    key_note = " (nøkkel lagret)" if pub_key else " (ingen nøkkel)"
    reply_fn(f"✅ {name} lagt til som privilegert node{key_note}.")


def handle_removepriv_command(text: str, reply_fn, ctx: BotContext) -> None:
    """Remove a node from the privileged list. Usage: /removepriv <node_id>"""
    db_conn = ctx.get("db_conn")
    parts = text.split()
    if len(parts) < 2:
        reply_fn("Bruk: /removepriv <node_id>")
        return
    target = parts[1]
    if db_conn is None:
        reply_fn("❌ Ingen database tilgjengelig.")
        return
    node = get_node(db_conn, target)
    remove_privileged_node(db_conn, target)
    name = (node.get("long_name") or node.get("short_name") or target) if node else target
    reply_fn(f"✅ {name} fjernet fra privilegerte noder.")


# ---------------------------------------------------------------------------
# Command registry — single source of truth for dispatch, help, and privileges.
# To add a command: add a Command entry here. Everything else is derived.
# ---------------------------------------------------------------------------

COMMAND_REGISTRY: list[Command] = [
    Command("/help",           handle_help_command,           "Vis hjelp"),
    Command("/ping",           handle_ping_command,           "Status og oppetid"),
    Command("/nodes",          handle_nodes_command,          "Vis noder på meshet"),
    Command("/weather",        handle_weather_command,        "7-dagers varsel (GPS)"),
    Command("/24hour",         handle_24h_command,            "24t timevarsel (GPS)", aliases=["/24h"]),
    Command("/radio",          handle_radio_command,          "HF/VHF båndkondisjon"),
    Command("/alert",          handle_alert_command,          "Sjekk aktive værvarsler nå"),
    Command("/whois",          handle_whois_command,          "Slå opp en node  <id/navn>"),
    Command("/bandplan",       handle_bandplan_command,       "Vis båndplan  <bånd>"),
    Command("/bandplan_check", handle_bandplan_check_command, "Sjekk frekvens  <freq>"),
    Command("/calling",        handle_calling_command,        "Anropsfrekvenser  <bånd>"),
    Command("/mvhf",           handle_mvhf_command,           "Marin VHF kanaler  [kanal]"),
    Command("/krslog",         handle_krslog_command,         "Meldingslogg  [t]"),
    Command("/krslast",        handle_krslast_command,        "Siste n meldinger  [n]"),
    Command("/addpriv",        handle_addpriv_command,        "Legg til privilegert node  <node_id>", privileged=True),
    Command("/removepriv",     handle_removepriv_command,     "Fjern privilegert node  <node_id>",    privileged=True),
]

# Derived dispatch table — includes aliases
COMMANDS: dict[str, callable] = {}
for _cmd in COMMAND_REGISTRY:
    COMMANDS[_cmd.name] = _cmd.handler
    for _alias in _cmd.aliases:
        COMMANDS[_alias] = _cmd.handler

# Derived privilege set
PRIVILEGED_COMMANDS: frozenset[str] = frozenset(
    c.name for c in COMMAND_REGISTRY if c.privileged
)
