# Copilot Instructions

## Project Overview

MeshtasticBot is a Python bot for interacting with [Meshtastic](https://meshtastic.org/) LoRa mesh network devices. It connects to devices over serial, BLE (via `bleak`), or D-Bus (via `dbus-fast`) and uses `pypubsub` for event-driven message handling.

It also pushes weather alerts from the Norwegian Meteorological Institute API (`api.met.no`), logs messages to SQLite, serves a Flask web UI, and can drive a Flipper Zero for privileged commands.

## Setup

```bash
pip install -r requirements.txt
```

The project uses a `.venv` virtualenv. Activate it before running:

```bash
source .venv/bin/activate
python src/main.py          # or ./run_dummy.sh for no-device dummy mode
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

- All source lives in `src/`. Entry point is `src/main.py`. Connection settings and target channel are read from `config.yaml` at startup.
- Meshtastic's Python SDK publishes incoming packets via `pypubsub`. Subscribe to `meshtastic.receive.text` for text messages; the packet dict includes `channel` (0-based int), `fromId` (string node ID), and `decoded.text`.
- Replies are sent with `interface.sendText(text, channelIndex=<n>)` for channel messages, or `interface.sendText(text, destinationId=<nodeId>, channelIndex=0)` for DMs.
- Direct messages are detected by checking `packet.get("toId") != "^all"`.
- **Commands are defined once in `COMMAND_REGISTRY` in `src/commands.py`.** Each handler has the signature `handler(text, reply_fn, ctx: BotContext) -> None`. Dispatch (`COMMANDS`), aliases, privilege gating (`PRIVILEGED_COMMANDS`) and `/help` pages are all derived from the registry.
- Connection type (serial / tcp / ble) is selected in `config.yaml` and resolved in the `connect()` function.
- The `api.met.no` weather alerts endpoint: `https://api.met.no/weatherapi/metalerts/2.0/all.json?county=<fylkesnummer>`
- **Web UI** (`web.py`) is a Flask app started as a daemon thread when `web.enabled: true` in `config.yaml`. Public pages: log viewer (`/`), status (`/status`), nodes (`/nodes`), map (`/map`), `/health`, and JSON APIs (`/api/messages`, `/api/nodes`, `/api/events` SSE). Admin pages/endpoints (`/audit`, `/admin/*`, `/api/send`, `/api/command`) use `@require_admin`. All DB access goes through `db.py` functions — no raw SQL in `web.py`. Templates live in `src/templates/` and use Bootstrap 5 via CDN.

## Bot Commands

| Command | Description |
|---|---|
| `/help` | Lists all available commands (two messages) |
| `/version` | Show bot version information |
| `/ping` | Bot status and uptime |
| `/nodes` | List nodes seen on the mesh |
| `/alert` | Check active weather alerts now |
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
| `/addpriv <node_id>` | Add a privileged node (privileged) |
| `/removepriv <node_id>` | Remove a privileged node (privileged) |
| `/awning <open\|close\|stop\|lights>` | Control the awning via Flipper Zero (privileged) |

**Rule: whenever a new command is added, add a `Command(...)` entry to `COMMAND_REGISTRY` in `src/commands.py`, add it to this table, and update the rate-limit cost comment in `config.yaml`.**

## Workflow Rules

- **All changes must go through a pull request — never commit directly to `main`.**
  Work on a feature branch, open a PR, wait for all GitHub Actions CI checks to pass, then merge.
  Do not consider a task complete until the PR is merged and CI is green.
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
- **Track new ideas and planned work as GitHub Issues, not in `IDEAS.md`.**
  When the user suggests a new idea or feature, create a GitHub issue using `gh issue create` with an appropriate label (`enhancement`, `reliability`, `ops`, `web-ui`, `testing`, `big-idea`). `IDEAS.md` is retained for historical reference only (completed ✅ items).

## Docker

- `Dockerfile` is multi-stage: the builder copies `src/`, `tests/` and `pyproject.toml` and runs pytest; the runtime stage copies `src/` and `pyproject.toml`. New files under `src/` are included automatically.
- `config.yaml` is mounted at runtime via `-v ./config.yaml:/app/config.yaml`, not baked into the image.
