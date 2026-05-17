# Copilot Instructions

## Project Overview

MeshtasticBot is a Python bot for interacting with [Meshtastic](https://meshtastic.org/) LoRa mesh network devices. It connects to devices over serial, BLE (via `bleak`), or D-Bus (via `dbus-fast`) and uses `pypubsub` for event-driven message handling.

A weather alerts integration using the Norwegian Meteorological Institute API (`api.met.no`) is planned/in progress.

## Setup

```bash
pip install -r requirements.txt
```

The project uses a `.venv` virtualenv. Activate it before running:

```bash
source .venv/bin/activate
python main.py
```

## Key Dependencies

| Package | Purpose |
|---|---|
| `meshtastic` | Core SDK for communicating with Meshtastic devices |
| `Pypubsub` | Event-driven pub/sub for handling incoming mesh messages |
| `bleak` | BLE transport for connecting to devices over Bluetooth |
| `pyserial` | Serial transport for USB-connected devices |
| `dbus-fast` | D-Bus transport (Linux) |
| `requests` | HTTP calls (e.g., weather API) |
| `PyYAML` | Config file parsing |

## Architecture Notes

- Entry point is `main.py`. Connection settings and target channel are read from `config.yaml` at startup.
- Meshtastic's Python SDK publishes incoming packets via `pypubsub`. Subscribe to `meshtastic.receive.text` for text messages; the packet dict includes `channel` (0-based int), `fromId` (string node ID), and `decoded.text`.
- Replies are sent with `interface.sendText(text, channelIndex=<n>)` for channel messages, or `interface.sendText(text, destinationId=<nodeId>, channelIndex=0)` for DMs.
- Direct messages are detected by checking `packet.get("toId") != "^all"`.
- **Bot logic lives entirely in `generate_reply(text, sender_id)`** — return a string to reply or `None` to stay silent.
- Connection type (serial / tcp / ble) is selected in `config.yaml` and resolved in the `connect()` function.
- The `api.met.no` weather alerts endpoint: `https://api.met.no/weatherapi/metalerts/2.0/all.json?county=<fylkesnummer>`
- **Web UI** (`web.py`) is a Flask app started as a daemon thread when `web.enabled: true` in `config.yaml`. It provides a read-only log viewer (`/`), status dashboard (`/status`), and JSON API (`/api/messages`). All DB reads go through `db.py` functions — no raw SQL in `web.py`. Templates live in `templates/` and use Bootstrap 5 via CDN.

## Bot Commands

| Command | Description |
|---|---|
| `/help` | Lists all available commands (two messages) |
| `/weather` | 7-day daily forecast from yr.no (requires node GPS position) |
| `/24hour` (`/24h`) | Hourly forecast for next 24 hours from yr.no (requires node GPS position) |
| `/radio` | Amateur radio HF/VHF band conditions, solar flux and K-index via HamQSL |
| `/bandplan <band>` | IARU Region 1 band plan for a specific band (e.g. `/bandplan 20m`). Supported: 160m, 80m, 60m, 40m, 30m, 20m, 17m, 15m, 12m, 10m, 6m, 2m, 70cm |
| `/bandplan_check <freq>` | Look up allowed usage for a frequency. Accepts MHz, kHz or bare number (e.g. `/bandplan_check 14.225`, `/bandplan_check 14225 kHz`) |
| `/calling <band>` | List calling frequencies for a band (IARU Region 1 / Norway) |
| `/mvhf [channel]` | List Marine VHF channels (ITU Region 1 / Norway), or look up a specific channel number (e.g. `/mvhf 16`) |
| `/whois <id/navn>` | Look up a node by exact ID (e.g. `/whois !aabbccdd`) or partial name (e.g. `/whois Alpha`) |
| `/krslog [t]` | Message log for the last t hours (default 24h, max 168h) |
| `/krslast [n]` | Last n messages from the log (default 10, max 100) |

**Rule: whenever a new command is added, always add it to both this table and the `HELP_MESSAGES` list in `main.py`.**

## Workflow Rules

- **Use test-driven development (TDD) whenever possible.**
  Write tests before or alongside the implementation, not after. A feature is not done until its tests are written and passing.
- **After making code changes, always run `ruff check src/ tests/` and fix any issues before committing.**
- **Before every commit, run `git status` to confirm nothing is accidentally left unstaged.**
  Use `git add -u` or `git add .` rather than listing files by name to avoid missing files modified by tools (e.g. `ruff --fix`).
- **After every commit, run `git push` to keep the remote in sync.**
- **Always use `len(s.encode("utf-8"))` to measure message size, never `len(s)`.**
  Meshtastic's byte limit is a hard constraint, and messages routinely contain
  multi-byte characters (Norwegian: ø, æ, å — and emojis: ⚡, 💨, 📻, 🟢).
  `len(s)` counts Unicode code points, not bytes, and will undercount silently.
- **When adding a new web page or API endpoint, always ask the user whether it needs authentication before implementing.**
  Current pages (logs, status, nodes, /api/messages) are intentionally unauthenticated. New pages may expose sensitive functionality and should be considered individually.

## Docker

- `Dockerfile` uses `COPY *.py ./` — all Python source files are included automatically. No manual updates needed when adding new `.py` files.
- `config.yaml` is mounted at runtime via `-v ./config.yaml:/app/config.yaml`, not baked into the image.
