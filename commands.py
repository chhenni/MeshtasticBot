"""
Command handlers for MeshtasticBot.

Each handle_*_command() function receives the raw text, a reply callable,
and any domain-specific dependencies (interface, db_conn, etc.).
"""

import time
import logging

from constants import PACK_BYTES, MAX_KRSLOG_HOURS, MAX_KRSLAST
from db import get_recent_messages, get_last_messages
from weather import (
    get_node_position,
    get_forecast, format_forecast_messages,
    get_forecast_24h, format_forecast_24h_messages,
)
from radio import get_radio_forecast, format_radio_messages
from bandplan import (
    BANDPLAN, CALLING_FREQUENCIES, resolve_band,
    format_bandplan_messages, format_calling_messages,
    parse_frequency_mhz, lookup_frequency,
)
from marine import format_mvhf_list_messages, format_mvhf_channel

log = logging.getLogger(__name__)


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
    "/krslog [t] - Meldingslogg (std: 24t, maks: 168t)\n"
    "/krslast [n] - Siste n meldinger (std: 10, maks: 100)",

    "Info [3/3]:\n"
    "- Kommandoer funker via DM\n"
    "- GPS må deles for værvarsler\n"
    "- Lynnvarsler og vindvarsler sendes automatisk",
]


def generate_reply(text: str, sender_id: str) -> str | None:
    """
    Return a reply string, or None to stay silent.
    Customize this function to implement your bot logic.
    Note: commands are handled separately in make_receive_handler.
    """
    return None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _send_pages(reply_fn, pages: list[str]) -> None:
    """Send a list of page strings, sleeping 3 s between each and adding
    [N/total] counters when there is more than one page."""
    total = len(pages)
    for i, page in enumerate(pages):
        if i > 0:
            time.sleep(3)
        reply_fn(f"[{i+1}/{total}] {page}" if total > 1 else page)


def _build_log_pages(rows: list[dict], header: str) -> list[str]:
    """Pack a list of log row dicts into byte-safe pages under PACK_BYTES."""
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
# Command handlers
# ---------------------------------------------------------------------------

def handle_help_command(reply_fn) -> None:
    for i, msg in enumerate(HELP_MESSAGES):
        if i > 0:
            time.sleep(2)
        reply_fn(msg)


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

    _send_pages(reply_fn, format_forecast_messages(forecast, lat, lon))


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

    _send_pages(reply_fn, format_forecast_24h_messages(forecast, lat, lon))


def handle_radio_command(reply_fn) -> None:
    """Fetch amateur radio band conditions and send as multi-message reply."""
    data = get_radio_forecast()
    if data is None:
        reply_fn("Klarte ikke hente radiokondisjon fra HamQSL.")
        return
    _send_pages(reply_fn, format_radio_messages(data))


def handle_calling_command(text: str, reply_fn) -> None:
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
        reply_fn(f"Bruk: /bandplan <bånd>\nTilgjengelig: {', '.join(BANDPLAN.keys())}")
        return

    band = resolve_band(parts[1])
    if band is None:
        reply_fn(f"Ukjent bånd '{parts[1]}'.\nTilgjengelig: {', '.join(BANDPLAN.keys())}")
        return

    log.info(f"/bandplan {band} requested")
    _send_pages(reply_fn, format_bandplan_messages(band))


def handle_mvhf_command(text: str, reply_fn) -> None:
    """List key Marine VHF channels, or look up a specific channel."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) >= 2 and parts[1].strip():
        reply_fn(format_mvhf_channel(parts[1].strip()))
        return
    _send_pages(reply_fn, format_mvhf_list_messages(groups=["Nød/DSC", "Havn/trafikk"]))


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


def handle_krslast_command(text: str, reply_fn, db_conn, log_channel: int) -> None:
    """Return the N most recent messages from the log channel. Default 10, max 100."""
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
