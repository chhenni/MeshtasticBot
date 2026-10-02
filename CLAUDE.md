# CLAUDE.md

MeshtasticBot is a Python 3.12+ bot for [Meshtastic](https://meshtastic.org/) LoRa mesh networks. It connects to a node over serial / TCP / BLE, answers slash-commands (mostly in Norwegian), logs messages to SQLite, pushes met.no weather alerts, serves a Flask web UI, and can drive a Flipper Zero (SubGHz) for privileged commands.

Derived from `.github/copilot-instructions.md`; keep the two in sync when rules or the command list change.

## Commands

```bash
source .venv/bin/activate
./run_tests.sh                 # pytest tests/ -v  (pass extra pytest args, e.g. -x or a file)
ruff check src/ tests/         # lint — line length 120, rules E,F,W,I
./run_dummy.sh [--channel N]   # run bot with no device (python src/main.py --dummy)
python src/main.py             # real run; reads config.yaml
```

CI (`.github/workflows/ci.yml`) runs `pip-audit`, `ruff check src/ tests/`, and `pytest -q` on Python 3.13. The Docker build also runs the test suite in its builder stage.

## Layout

All source is in `src/` (pytest `pythonpath = ["src"]`, so tests import modules flatly: `from commands import ...`).

| File | Role |
|---|---|
| `main.py` | Entry point, config load/validate, env overrides, `connect()`, receive handler (dedup, rate limit, privilege check, dispatch), background loops, SIGHUP reload |
| `commands.py` | All command handlers + `COMMAND_REGISTRY` |
| `context.py` | `BotContext` TypedDict passed to handlers |
| `constants.py` | `MAX_BYTES` (200), `PACK_BYTES`, limits |
| `db.py` | All SQLite access (messages, nodes, audit, bans, privileged nodes) |
| `web.py` | Flask app (daemon thread), SSE live updates, REST API |
| `weather.py`, `radio.py`, `bandplan.py`, `marine.py` | Feature modules (yr.no / met.no, HamQSL, IARU R1, marine VHF) |
| `flipper.py` | Flipper Zero serial SubGHz sender |
| `dummy.py` | `DummyInterface` for running without hardware |
| `log_config.py` | structlog setup — use `log = structlog.get_logger()` and event-style keys (`log.info("message_sent", to=...)`) |
| `templates/` | Jinja templates, Bootstrap 5 via CDN, Leaflet map |

## Architecture notes

- **Commands**: every handler has the signature `handler(text: str, reply_fn, ctx: BotContext) -> None`. Commands are defined once in `COMMAND_REGISTRY` in `src/commands.py`; dispatch (`COMMANDS`), aliases, `PRIVILEGED_COMMANDS`, and `/help` pages are all derived from it. To add a command: write the handler, add a `Command(...)` entry, add tests, and add a row to the command table in `.github/copilot-instructions.md`.
- Rate-limit cost per command is documented in `config.yaml`; keep that comment current when adding commands.
- Incoming packets come via pypubsub (`meshtastic.receive.text`). DMs are detected by `packet["toId"] != "^all"`; DM replies use `destinationId=<sender>, channelIndex=0`, channel replies use `channelIndex=<channel>`. Sends go through `send_text_with_retry`.
- Packets are deduplicated by packet ID (relayed copies).
- Config: `config.yaml`, overridable by env vars `MESHTASTIC__SECTION__KEY` (type inferred from the YAML value). Reloaded on SIGHUP.
- Shared runtime state lives in the `bot_state` dict, which the web app also reads (e.g. `flipper_cfg`).
- **Web**: no raw SQL in `web.py`; all DB access goes through `db.py`. Admin pages/endpoints use `@require_admin` (HTTP basic auth from `admin:` config). Public: `/`, `/status`, `/nodes`, `/map`, `/health`, `/api/messages`, `/api/nodes`, `/api/events`. API docs are in `docs/api/`.
- Bot-facing text (replies, help) is in Norwegian; code, comments, and logs are in English.

## Rules (from copilot-instructions, still binding)

- **Never commit directly to `main`.** Branch (`feature/...`, `fix/...`), open a PR with `gh`, wait for CI to be green, then merge. A task isn't done until the PR is merged with green CI.
- **TDD where possible**: write tests before or alongside the implementation. Tests must not hit the network; patch external calls (and `time.sleep`, scoped narrowly; see commit 3fe2c57, where a broad patch broke Flipper serial timing).
- Run `ruff check src/ tests/` and fix issues before every commit.
- Run `git status` before committing; stage with `git add -u` / `git add .` so files modified by tools (e.g. `ruff --fix`) aren't missed.
- `git push` after every commit.
- **Measure message size with `len(s.encode("utf-8"))`, never `len(s)`.** Meshtastic's limit is in bytes and messages contain ø/æ/å and emoji. Keep messages ≤ `MAX_BYTES`; paginate long output (`PACK_BYTES` reserves room for `[NN/NN]` prefixes).
- **Ask the user whether a new web page or API endpoint needs authentication before implementing it.**
- **Track new ideas as GitHub Issues** (`gh issue create`, labels: `enhancement`, `reliability`, `ops`, `web-ui`, `testing`, `big-idea`), not in `IDEAS.md` (historical only).

## Docker

- Multi-stage `Dockerfile`: builder copies `src/`, `tests/`, `pyproject.toml` and runs pytest; runtime copies `src/` + `pyproject.toml`. New files under `src/` are picked up automatically.
- `config.yaml` is mounted at runtime, never baked in. Devices are mapped via udev symlinks (`/dev/meshtastic`, `/dev/flipper`; see `docs/udev-setup.md`).
- Image version comes from GitVersion in CI (`APP_VERSION` build arg), falling back to `pyproject.toml`.
