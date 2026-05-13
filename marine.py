"""
Marine VHF channel plan for Norway.
Source: kanalplan.no (Nordic coast radio channel plan), ITU Radio Regulations App. 18.

Each channel entry:
  "tx":     Ship transmit frequency (MHz)
  "rx":     Ship receive frequency (MHz) — same as tx for simplex
  "duplex": True if ship-tx != coast-rx
  "usage":  Norwegian usage description

Dict keys are strings to accommodate non-numeric channels (AIS1, L1, F1, etc.)
"""

MARINE_VHF: dict[str, dict] = {
    # --- Nød / DSC ---
    "16":  {"tx": 156.800, "rx": 156.800, "duplex": False, "usage": "Nød- og kallekanal (obligatorisk lyttvakt)"},
    "70":  {"tx": 156.525, "rx": 156.525, "duplex": False, "usage": "DSC nødanrop (kun digitalt, ikke tale)"},

    # --- Havn / Trafikk / Los ---
    "12":  {"tx": 156.600, "rx": 156.600, "duplex": False, "usage": "Havnetjeneste"},
    "13":  {"tx": 156.650, "rx": 156.650, "duplex": False, "usage": "Lostjeneste"},
    "18":  {"tx": 156.900, "rx": 161.500, "duplex": True,  "usage": "VTS-tjeneste"},
    "19":  {"tx": 156.950, "rx": 161.550, "duplex": True,  "usage": "VTS-tjeneste"},

    # --- Skip-skip (simplex) ---
    "06":  {"tx": 156.300, "rx": 156.300, "duplex": False, "usage": "Skip-skip"},
    "08":  {"tx": 156.400, "rx": 156.400, "duplex": False, "usage": "Skip-skip"},
    "09":  {"tx": 156.450, "rx": 156.450, "duplex": False, "usage": "Skip-skip"},
    "10":  {"tx": 156.500, "rx": 156.500, "duplex": False, "usage": "Skip-skip"},
    "11":  {"tx": 156.550, "rx": 156.550, "duplex": False, "usage": "Skip-skip"},
    "14":  {"tx": 156.700, "rx": 156.700, "duplex": False, "usage": "Skip-skip"},
    "15":  {"tx": 156.750, "rx": 156.750, "duplex": False, "usage": "Skip-skip (maks 1W, nær ch16)"},
    "17":  {"tx": 156.850, "rx": 156.850, "duplex": False, "usage": "Skip-skip (maks 1W, nær ch16)"},
    "67":  {"tx": 156.375, "rx": 156.375, "duplex": False, "usage": "Skip-skip / SAR / Kystvakt"},
    "68":  {"tx": 156.425, "rx": 156.425, "duplex": False, "usage": "Skip-skip"},
    "69":  {"tx": 156.475, "rx": 156.475, "duplex": False, "usage": "Skip-skip"},
    "71":  {"tx": 156.575, "rx": 156.575, "duplex": False, "usage": "Skip-skip"},
    "72":  {"tx": 156.625, "rx": 156.625, "duplex": False, "usage": "Skip-skip (brukes av helikopter)"},
    "73":  {"tx": 156.675, "rx": 156.675, "duplex": False, "usage": "Skip-skip"},
    "74":  {"tx": 156.725, "rx": 156.725, "duplex": False, "usage": "Skip-skip"},
    "75":  {"tx": 156.775, "rx": 156.775, "duplex": False, "usage": "Skip-skip (maks 1W, nær ch70)"},
    "76":  {"tx": 156.825, "rx": 156.825, "duplex": False, "usage": "Skip-skip (maks 1W, nær ch70)"},
    "77":  {"tx": 156.875, "rx": 156.875, "duplex": False, "usage": "Skip-skip"},
    "87":  {"tx": 157.375, "rx": 157.375, "duplex": False, "usage": "Skip-skip"},
    "88":  {"tx": 157.425, "rx": 157.425, "duplex": False, "usage": "Skip-skip"},

    # --- Kystradio (duplex) ---
    "01":  {"tx": 156.050, "rx": 160.650, "duplex": True,  "usage": "Kystradiostasjon"},
    "02":  {"tx": 156.100, "rx": 160.700, "duplex": True,  "usage": "Kystradiostasjon"},
    "03":  {"tx": 156.150, "rx": 160.750, "duplex": True,  "usage": "Kystradiostasjon"},
    "04":  {"tx": 156.200, "rx": 160.800, "duplex": True,  "usage": "Kystradiostasjon"},
    "05":  {"tx": 156.250, "rx": 160.850, "duplex": True,  "usage": "Kystradiostasjon"},
    "07":  {"tx": 156.350, "rx": 160.950, "duplex": True,  "usage": "Kystradiostasjon"},
    "20":  {"tx": 157.000, "rx": 161.600, "duplex": True,  "usage": "Kystradiostasjon"},
    "21":  {"tx": 157.050, "rx": 161.650, "duplex": True,  "usage": "Kystradiostasjon"},
    "22":  {"tx": 157.100, "rx": 161.700, "duplex": True,  "usage": "Kystradiostasjon"},
    "23":  {"tx": 157.150, "rx": 161.750, "duplex": True,  "usage": "Kystradiostasjon"},
    "24":  {"tx": 157.200, "rx": 161.800, "duplex": True,  "usage": "Kystradiostasjon"},
    "25":  {"tx": 157.250, "rx": 161.850, "duplex": True,  "usage": "Kystradiostasjon"},
    "26":  {"tx": 157.300, "rx": 161.900, "duplex": True,  "usage": "Kystradiostasjon"},
    "27":  {"tx": 157.350, "rx": 161.950, "duplex": True,  "usage": "Kystradiostasjon"},
    "28":  {"tx": 157.400, "rx": 162.000, "duplex": True,  "usage": "Kystradiostasjon"},
    "60":  {"tx": 156.025, "rx": 160.625, "duplex": True,  "usage": "Kystradiostasjon"},
    "61":  {"tx": 156.075, "rx": 160.675, "duplex": True,  "usage": "Kystradiostasjon"},
    "62":  {"tx": 156.125, "rx": 160.725, "duplex": True,  "usage": "Kystradiostasjon"},
    "63":  {"tx": 156.175, "rx": 160.775, "duplex": True,  "usage": "Kystradiostasjon"},
    "64":  {"tx": 156.225, "rx": 160.825, "duplex": True,  "usage": "Kystradiostasjon"},
    "65":  {"tx": 156.275, "rx": 160.875, "duplex": True,  "usage": "Kystradiostasjon"},
    "66":  {"tx": 156.325, "rx": 160.925, "duplex": True,  "usage": "Kystradiostasjon"},
    "78":  {"tx": 156.925, "rx": 161.525, "duplex": True,  "usage": "Kystradiostasjon"},
    "79":  {"tx": 156.975, "rx": 161.575, "duplex": True,  "usage": "Kystradiostasjon"},
    "80":  {"tx": 157.025, "rx": 161.625, "duplex": True,  "usage": "Kystradiostasjon"},
    "81":  {"tx": 157.075, "rx": 161.675, "duplex": True,  "usage": "Kystradiostasjon"},
    "82":  {"tx": 157.125, "rx": 161.725, "duplex": True,  "usage": "Kystradiostasjon"},
    "83":  {"tx": 157.175, "rx": 161.775, "duplex": True,  "usage": "Kystradiostasjon"},
    "84":  {"tx": 157.225, "rx": 161.825, "duplex": True,  "usage": "Kystradiostasjon"},
    "85":  {"tx": 157.275, "rx": 161.875, "duplex": True,  "usage": "Kystradiostasjon"},
    "86":  {"tx": 157.325, "rx": 161.925, "duplex": True,  "usage": "Kystradiostasjon"},

    # --- Lystbåt (kun Norge / Norden) ---
    "L1":  {"tx": 155.500, "rx": 155.500, "duplex": False, "usage": "Lystbåt skip-skip (kun Norge)"},
    "L2":  {"tx": 155.525, "rx": 155.525, "duplex": False, "usage": "Lystbåt skip-skip (kun Norge)"},
    "L3":  {"tx": 155.650, "rx": 155.650, "duplex": False, "usage": "Lystbåt skip-skip (kun Norge)"},

    # --- Fiskebåt (kun Norge / Norden) ---
    "F1":  {"tx": 155.625, "rx": 155.625, "duplex": False, "usage": "Fiskebåt skip-skip (kun Norge)"},
    "F2":  {"tx": 155.775, "rx": 155.775, "duplex": False, "usage": "Fiskebåt skip-skip (kun Norge)"},
    "F3":  {"tx": 155.825, "rx": 155.825, "duplex": False, "usage": "Fiskebåt skip-skip (kun Norge)"},

    # --- AIS / Datakanaler ---
    "AIS1": {"tx": 161.975, "rx": 161.975, "duplex": False, "usage": "AIS-data"},
    "AIS2": {"tx": 162.025, "rx": 162.025, "duplex": False, "usage": "AIS-data"},
    "ASM1": {"tx": 161.950, "rx": 161.950, "duplex": False, "usage": "Application Specific Messages"},
    "ASM2": {"tx": 162.000, "rx": 162.000, "duplex": False, "usage": "Application Specific Messages"},
}

# Grouped order for the list command
MARINE_VHF_GROUPS: list[tuple[str, list[str]]] = [
    ("Nød/DSC",       ["16", "70"]),
    ("Havn/trafikk",  ["12", "13", "18", "19"]),
    ("Skip-skip",     ["06", "08", "09", "10", "11", "14", "15", "17",
                       "67", "68", "69", "71", "72", "73", "74", "75", "76", "77", "87", "88"]),
    ("Kystradio",     ["01", "02", "03", "04", "05", "07",
                       "20", "21", "22", "23", "24", "25", "26", "27", "28",
                       "60", "61", "62", "63", "64", "65", "66",
                       "78", "79", "80", "81", "82", "83", "84", "85", "86"]),
    ("Lystbåt",       ["L1", "L2", "L3"]),
    ("Fiskebåt",      ["F1", "F2", "F3"]),
    ("AIS/data",      ["AIS1", "AIS2", "ASM1", "ASM2"]),
]


def _normalize_key(raw: str) -> str:
    """Normalize user input to a MARINE_VHF key (e.g. '6' -> '06', 'l1' -> 'L1')."""
    upper = raw.strip().upper()
    # Alpha-prefix channels: L1, L2, F1, AIS1, ASM2, etc.
    if not upper.isdigit():
        return upper
    # Numeric: zero-pad to 2 digits
    n = int(upper)
    return f"{n:02d}"


def format_mvhf_channel(raw: str) -> str:
    """Return a single formatted string for one Marine VHF channel."""
    key = _normalize_key(raw)
    ch = MARINE_VHF.get(key)
    if ch is None:
        return f"Kanal {raw} finnes ikke i norsk kanalplan."

    if ch["duplex"]:
        freq = f"Tx {ch['tx']:.3f} / Rx {ch['rx']:.3f} MHz (duplex)"
    else:
        freq = f"{ch['tx']:.3f} MHz (simplex)"

    return f"Marin VHF kanal {key}:\n{freq}\n{ch['usage']}"


def format_mvhf_list_messages(groups: list[str] | None = None) -> list[str]:
    """
    Format Marine VHF channels grouped by category into Meshtastic-safe messages (<=200 UTF-8 bytes).
    If `groups` is given, only those group names are included.
    """
    MAX_BYTES = 200
    # Reserve space for worst-case page prefix like "[14/14] " = 8 bytes
    PACK_BYTES = MAX_BYTES - 8

    lines: list[str] = []
    for group_name, channels in MARINE_VHF_GROUPS:
        if groups is not None and group_name not in groups:
            continue
        lines.append(f"== {group_name} ==")
        seen: set[str] = set()
        for key in channels:
            if key in seen or key not in MARINE_VHF:
                continue
            seen.add(key)
            ch = MARINE_VHF[key]
            duplex_marker = "D" if ch["duplex"] else "S"
            lines.append(f"Ch{key} {ch['tx']:.3f}({duplex_marker}) {ch['usage']}")

    pages: list[str] = []
    current: list[str] = []

    for line in lines:
        if not current:
            current.append(line)
            continue
        candidate = "\n".join(current + [line])
        if len(candidate.encode("utf-8")) > PACK_BYTES:
            pages.append("\n".join(current))
            current = [line]
        else:
            current.append(line)

    if current:
        pages.append("\n".join(current))

    total = len(pages)
    if total == 1:
        return pages
    return [f"[{i + 1}/{total}] {page}" for i, page in enumerate(pages)]
