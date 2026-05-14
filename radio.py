"""
Amateur radio band forecast via the HamQSL solar data API.
"""

import logging
import xml.etree.ElementTree as ET

import requests

from constants import MAX_BYTES, USER_AGENT

log = logging.getLogger(__name__)

HAMQSL_URL = "https://www.hamqsl.com/solarxml.php"

_CONDITION_EMOJI = {"Good": "🟢", "Fair": "🟡", "Poor": "🔴"}
_VHF_LOCATION_LABEL = {
    "northern_hemi": "Aurora",
    "europe": "E-skip EU",
    "north_america": "E-skip NA",
    "europe_6m": "E-skip 6m",
    "europe_4m": "E-skip 4m",
}


def get_radio_forecast() -> dict | None:
    """Fetch solar and band condition data from HamQSL. Returns None on error."""
    try:
        resp = requests.get(HAMQSL_URL, headers={"User-Agent": USER_AGENT}, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        sd = root.find("solardata")
        if sd is None:
            return None
    except (requests.RequestException, ET.ParseError) as e:
        log.error(f"Failed to fetch radio forecast: {e}")
        return None

    def txt(tag: str) -> str:
        el = sd.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    hf_bands: dict[str, dict] = {}
    for band_el in sd.findall("calculatedconditions/band"):
        name = band_el.get("name", "")
        time = band_el.get("time", "")
        cond = band_el.text.strip() if band_el.text else ""
        hf_bands.setdefault(name, {})[time] = cond

    vhf: list[tuple[str, str]] = []
    for ph in sd.findall("calculatedvhfconditions/phenomenon"):
        loc = ph.get("location", "")
        label = _VHF_LOCATION_LABEL.get(loc, loc)
        cond = ph.text.strip() if ph.text else ""
        if cond and cond.lower() != "band closed":
            vhf.append((label, cond))

    return {
        "sfi": txt("solarflux"),
        "kindex": txt("kindex"),
        "aindex": txt("aindex"),
        "geomagfield": txt("geomagfield"),
        "signalnoise": txt("signalnoise"),
        "updated": txt("updated"),
        "hf_bands": hf_bands,
        "vhf": vhf,
    }


def format_radio_messages(data: dict) -> list[str]:
    """Format radio forecast into Meshtastic-safe messages (<=200 UTF-8 bytes each)."""
    lines = [
        f"📻 Radiokondisjon ({data['updated']}):",
        f"SFI:{data['sfi']} K:{data['kindex']} A:{data['aindex']}",
        f"Geo: {data['geomagfield']}  Støy: {data['signalnoise']}",
        "--- HF bånd ---",
    ]

    for band, times in data["hf_bands"].items():
        day = times.get("day", "?")
        night = times.get("night", "?")
        d_icon = _CONDITION_EMOJI.get(day, "")
        n_icon = _CONDITION_EMOJI.get(night, "")
        lines.append(f"{band}: dag {d_icon}{day} / natt {n_icon}{night}")

    if data["vhf"]:
        lines.append("--- VHF ---")
        for label, cond in data["vhf"]:
            lines.append(f"{label}: {cond}")

    # Pack into byte-safe pages
    pages: list[str] = []
    current_lines: list[str] = []
    for line in lines:
        candidate = "\n".join(current_lines + [line])
        if current_lines and len(candidate.encode("utf-8")) > MAX_BYTES:
            pages.append("\n".join(current_lines))
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        pages.append("\n".join(current_lines))

    total = len(pages)
    if total == 1:
        return pages
    return [f"[{i + 1}/{total}] {page}" for i, page in enumerate(pages)]
