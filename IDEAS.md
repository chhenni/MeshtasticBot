# Ideas & Future Work

## Small / quick wins

- ✅ **`/ping`** — bot replies with uptime and node count, useful for checking the mesh is alive
- ✅ **`/nodes`** — list currently seen nodes on the mesh with signal strength (RSSI/SNR)
- ✅ **Rate limiting** — ignore repeated commands from the same sender within N seconds to prevent spam
- ✅ **Config validation** — fail fast at startup with a clear error if `config.yaml` is missing required fields
- ✅ **GitHub Actions CI** — run the test suite automatically on push
- ✅ **Environment variable config overrides** — any `MESHTASTIC__SECTION__KEY` env var overlays `config.yaml` at startup; type is inferred from the YAML value so no hardcoded mapping is needed

## Medium effort

- **`/tide <location>`** — Norwegian tide tables from `api.sehavniva.no` (free Norwegian government API, same pattern as yr.no)
- ✅ **`/alert`** — on-demand weather alert check, not just the background loop
- **Per-command rate limiting** — currently rate limiting is per-sender globally; extend to key on `(sender, command)` so e.g. `/weather` can have its own cooldown independent of `/ping`
- ✅ **Burst-tolerant rate limiting** — token bucket with command-cost weighting. Bucket size 5, refill 1 token/10s. /ping /help /whois cost 1, /nodes /radio /alert /calling /mvhf cost 2, /weather /24hour /bandplan /krslog /krslast cost 3.
- **Web UI authentication** — simple IP whitelist or API key to protect the message log from open network access
- **Config validation improvements** — add checks for `retain_days > 0`, port range 1–65535, county as 2-digit string, `rate_limit_seconds >= 0`
- **`/health` endpoint** — `GET /health` returns JSON with uptime, last message timestamp, DB size — useful for external monitoring
- **Web route tests** — `tests/test_web.py` with Flask `test_client()` covering `/`, `/status`, `/nodes`, `/api/messages`
- ✅ **Command audit log** — persists every bot command (node ID, command, timestamp, status: ok/rate_limited/banned) to `command_log` in SQLite. `/audit` web page with filters and ban/unban buttons, protected by HTTP Basic Auth.
- ✅ **User ban system** — `banned_nodes` table in SQLite. Banned nodes are silently ignored before the token bucket check. Managed via the `/audit` web page (admin credentials required).

## Reliability & correctness

- ✅ **SQLite WAL mode** — enable `PRAGMA journal_mode=WAL` + `busy_timeout=5000` in `init_db()` to prevent `SQLITE_BUSY` errors under concurrent writes from the receiver, purge loop, node sync loop and Flask threads. Two-liner fix, high impact.
- ✅ **Connection reconnect** — if the Meshtastic device disconnects, the bot currently dies; add exponential backoff retry around `connect()` so it recovers automatically
- **Graceful shutdown** — all background threads are `daemon=True` and get killed abruptly on exit; add a `shutdown_event` + signal handlers (SIGTERM/SIGINT) so Flask, DB writes and the weather loop can finish cleanly
- **Typed `ctx` dict** — handlers assume specific keys exist in `ctx` and crash if missing; replace the plain `dict` with a `TypedDict` or dataclass so key errors are caught by type checkers

## Bigger ideas

- ✅ **Persistent node registry** — store seen nodes in the DB, track last-seen time, build a `/whois !abc123` command
- **Repeater/relay mode** — forward messages between channels or to a webhook (Slack, Discord, Telegram)
- **APRS bridge** — Meshtastic positions → APRS-IS, so nodes show up on aprs.fi
- **Web UI enhancements** — live updates via SSE/WebSocket, map view of node positions using Leaflet.js
- **Keyset pagination** — replace `OFFSET`-based paging in `db.py` with cursor-based keyset pagination for performance on large message tables
- **Structured logging** — JSON log output (e.g. via `structlog`) for easier ops monitoring and log aggregation
- ✅ **Dependency audit in CI** — `pip-audit` step in `.github/workflows/ci.yml` checks `requirements.txt` for known CVEs on every push/PR
- **Config reload on SIGHUP** — reload `config.yaml` without restarting the bot, useful for changing county or rate limits in production
