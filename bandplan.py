"""
Amateur radio band plan for Norway (IARU Region 1).
Source: IARU Region 1 HF band plan (effective 2020) and VHF/UHF band plans.
"""

# Each band entry:
#   "range": human-readable frequency range
#   "segments": list of (freq_range_str, mode_description)
BANDPLAN: dict[str, dict] = {
    "160m": {
        "range": "1.810-2.000 MHz",
        "segments": [
            ("1.810-1.838", "CW"),
            ("1.838-1.840", "CW/Digital"),
            ("1.840-1.843", "Digital bredbånd"),
            ("1.843-2.000", "SSB/AM/Digital"),
        ],
    },
    "80m": {
        "range": "3.500-3.800 MHz",
        "segments": [
            ("3.500-3.510", "CW (DX)"),
            ("3.510-3.560", "CW (contest)"),
            ("3.560-3.580", "CW (QRP: 3.560)"),
            ("3.580-3.600", "Digital bredbånd"),
            ("3.600-3.620", "Digital/SSB"),
            ("3.620-3.650", "SSB/Digital"),
            ("3.650-3.700", "SSB"),
            ("3.700-3.775", "SSB (contest)"),
            ("3.775-3.800", "SSB (DX)"),
        ],
    },
    "60m": {
        "range": "5.3515-5.3665 MHz",
        "segments": [
            ("5.351.5-5.354.0", "CW/Digital (maks 15W)"),
            ("5.354.0-5.366.0", "SSB/Digital (maks 15W)"),
            ("5.366.0-5.366.5", "Svak signal (maks 1W)"),
        ],
    },
    "40m": {
        "range": "7.000-7.200 MHz",
        "segments": [
            ("7.000-7.040", "CW"),
            ("7.040-7.047", "Digital bredbånd"),
            ("7.047-7.050", "Digital/CW"),
            ("7.050-7.053", "Digital"),
            ("7.053-7.060", "Digital/SSB"),
            ("7.060-7.100", "SSB (7.090 QRP)"),
            ("7.100-7.130", "SSB"),
            ("7.130-7.175", "SSB (contest)"),
            ("7.175-7.200", "SSB (DX)"),
        ],
    },
    "30m": {
        "range": "10.100-10.150 MHz",
        "segments": [
            ("10.100-10.130", "CW"),
            ("10.130-10.150", "Digital"),
        ],
    },
    "20m": {
        "range": "14.000-14.350 MHz",
        "segments": [
            ("14.000-14.060", "CW (DX: 14.025)"),
            ("14.060-14.070", "CW (QRP: 14.060)"),
            ("14.070-14.099", "Digital"),
            ("14.099-14.101", "Fyrtårn/IBP"),
            ("14.101-14.112", "Digital/auto"),
            ("14.112-14.125", "Alle moder"),
            ("14.125-14.300", "SSB (SSTV: 14.230)"),
            ("14.300-14.350", "SSB/Alle moder"),
        ],
    },
    "17m": {
        "range": "18.068-18.168 MHz",
        "segments": [
            ("18.068-18.095", "CW"),
            ("18.095-18.105", "CW/Digital (QRP: 18.096)"),
            ("18.105-18.109", "Digital"),
            ("18.109-18.111", "Fyrtårn/IBP"),
            ("18.111-18.168", "SSB/Alle moder"),
        ],
    },
    "15m": {
        "range": "21.000-21.450 MHz",
        "segments": [
            ("21.000-21.070", "CW (DX: 21.025)"),
            ("21.070-21.110", "Digital"),
            ("21.110-21.120", "Digital/CW (QRP: 21.110)"),
            ("21.120-21.149", "CW"),
            ("21.149-21.151", "Fyrtårn/IBP"),
            ("21.151-21.450", "SSB (SSTV: 21.340)"),
        ],
    },
    "12m": {
        "range": "24.890-24.990 MHz",
        "segments": [
            ("24.890-24.915", "CW"),
            ("24.915-24.929", "Digital (QRP: 24.906)"),
            ("24.929-24.931", "Fyrtårn/IBP"),
            ("24.931-24.990", "SSB/Alle moder"),
        ],
    },
    "10m": {
        "range": "28.000-29.700 MHz",
        "segments": [
            ("28.000-28.070", "CW (DX: 28.025)"),
            ("28.070-28.190", "Digital"),
            ("28.190-28.225", "Fyrtårn/IBP"),
            ("28.225-28.300", "Fyrtårn"),
            ("28.300-28.320", "Digital/SSB"),
            ("28.320-29.000", "SSB (QRP: 28.360)"),
            ("29.000-29.200", "FM/AM/Alle moder"),
            ("29.200-29.300", "Digital"),
            ("29.300-29.510", "Satelitt"),
            ("29.510-29.700", "FM (rep. inn: 29.520-29.590)"),
        ],
    },
    "6m": {
        "range": "50.000-52.000 MHz",
        "segments": [
            ("50.000-50.100", "CW/SSB (Fyrtårn: 50.000-50.030)"),
            ("50.100-50.200", "SSB/CW (DX: 50.110)"),
            ("50.200-50.300", "SSB/CW"),
            ("50.300-50.400", "Alle moder"),
            ("50.400-50.500", "Fyrtårn"),
            ("50.500-51.000", "Alle moder"),
            ("51.000-52.000", "FM (rep: 51.210-51.390)"),
        ],
    },
    "2m": {
        "range": "144-146 MHz",
        "segments": [
            ("144.000-144.025", "EME/CW"),
            ("144.025-144.100", "CW"),
            ("144.100-144.150", "CW/SSB (QRP: 144.050)"),
            ("144.150-144.400", "SSB/CW (anrop: 144.300)"),
            ("144.400-144.490", "Fyrtårn"),
            ("144.500-144.794", "Alle moder/Digital"),
            ("144.800-144.990", "Digital (APRS: 144.800)"),
            ("145.000-145.575", "FM (rep: 145.600-145.775)"),
            ("145.575-145.800", "FM/Alle moder"),
            ("145.800-146.000", "Satelitt"),
        ],
    },
    "70cm": {
        "range": "430-440 MHz",
        "segments": [
            ("430.000-430.400", "Alle moder"),
            ("430.400-430.575", "Digital/Repeater"),
            ("430.600-431.975", "FM-repeater (ut)"),
            ("432.000-432.100", "EME/CW/SSB"),
            ("432.100-432.400", "SSB/CW (anrop: 432.200)"),
            ("432.400-432.490", "Fyrtårn"),
            ("432.500-432.975", "Alle moder/Digital"),
            ("433.000-433.375", "FM (anrop: 433.500)"),
            ("433.400-433.575", "Digital"),
            ("434.000-434.990", "ATV/Digital"),
            ("435.000-438.000", "Satelitt"),
            ("438.025-439.975", "FM-repeater (inn)"),
        ],
    },
}

# Aliases for common alternate band names
BAND_ALIASES: dict[str, str] = {
    "1.8m": "160m", "1.8": "160m", "160": "160m",
    "3.5m": "80m",  "3.5": "80m",  "80": "80m",
    "5m": "60m",    "5": "60m",    "60": "60m",
    "7m": "40m",    "7": "40m",    "40": "40m",
    "10m": "10m",   "10": "10m",   "28m": "10m",
    "12m": "12m",   "12": "12m",   "24m": "12m",
    "15m": "15m",   "15": "15m",   "21m": "15m",
    "17m": "17m",   "17": "17m",   "18m": "17m",
    "20m": "20m",   "20": "20m",   "14m": "20m",
    "30m": "30m",   "30": "30m",
    "40m": "40m",
    "6m": "6m",     "6": "6m",     "50m": "6m",
    "2m": "2m",     "2": "2m",     "144m": "2m",
    "70cm": "70cm", "70": "70cm",  "430m": "70cm", "0.7m": "70cm",
}


def resolve_band(name: str) -> str | None:
    """Normalise user input to a canonical band key, e.g. '20' -> '20m'."""
    key = name.strip().lower()
    if key in BANDPLAN:
        return key
    return BAND_ALIASES.get(key)


def format_bandplan_messages(band: str) -> list[str]:
    """
    Format the band plan for a given band into Meshtastic-safe messages (<=200 UTF-8 bytes).
    """
    MAX_BYTES = 200
    entry = BANDPLAN[band]
    header = f"Båndplan {band} ({entry['range']}):"
    lines = [f"{freq}: {mode}" for freq, mode in entry["segments"]]

    pages: list[str] = []
    current_lines: list[str] = []
    include_header = True

    for line in lines:
        candidate = (header + "\n" + "\n".join(current_lines + [line])
                     if include_header else "\n".join(current_lines + [line]))
        if current_lines and len(candidate.encode("utf-8")) > MAX_BYTES:
            pages.append(header + "\n" + "\n".join(current_lines)
                         if include_header else "\n".join(current_lines))
            current_lines = [line]
            include_header = False
        else:
            current_lines.append(line)

    if current_lines:
        pages.append(header + "\n" + "\n".join(current_lines)
                     if include_header else "\n".join(current_lines))

    total = len(pages)
    if total == 1:
        return pages
    return [f"[{i + 1}/{total}] {page}" for i, page in enumerate(pages)]
