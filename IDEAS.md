# Ideas & Future Work

## Small / quick wins

- ✅ **`/ping`** — bot replies with uptime and node count, useful for checking the mesh is alive
- ✅ **`/nodes`** — list currently seen nodes on the mesh with signal strength (RSSI/SNR)
- ✅ **Rate limiting** — ignore repeated commands from the same sender within N seconds to prevent spam
- ✅ **Config validation** — fail fast at startup with a clear error if `config.yaml` is missing required fields
- ✅ **GitHub Actions CI** — run the test suite automatically on push

## Medium effort

- **`/tide <location>`** — Norwegian tide tables from `api.sehavniva.no` (free Norwegian government API, same pattern as yr.no)
- ✅ **`/alert`** — on-demand weather alert check, not just the background loop
- **`/krssearch <term>`** — search the log DB by keyword
- **Per-command rate limiting** — currently rate limiting is per-sender globally; extend to key on `(sender, command)` so e.g. `/weather` can have its own cooldown independent of `/ping`
- **Web UI authentication** — simple IP whitelist or API key to protect the message log from open network access
- **Config validation improvements** — add checks for `retain_days > 0`, port range 1–65535, county as 2-digit string, `rate_limit_seconds >= 0`
- **`/health` endpoint** — `GET /health` returns JSON with uptime, last message timestamp, DB size — useful for external monitoring
- **Web route tests** — `tests/test_web.py` with Flask `test_client()` covering `/`, `/status`, `/nodes`, `/api/messages`
- **Main integration test** — `tests/test_main.py` covering full startup → config → handler dispatch flow

## Reliability & correctness

- ✅ **SQLite WAL mode** — enable `PRAGMA journal_mode=WAL` + `busy_timeout=5000` in `init_db()` to prevent `SQLITE_BUSY` errors under concurrent writes from the receiver, purge loop, node sync loop and Flask threads. Two-liner fix, high impact.
- **Connection reconnect** — if the Meshtastic device disconnects, the bot currently dies; add exponential backoff retry around `connect()` so it recovers automatically
- **Graceful shutdown** — all background threads are `daemon=True` and get killed abruptly on exit; add a `shutdown_event` + signal handlers (SIGTERM/SIGINT) so Flask, DB writes and the weather loop can finish cleanly
- **Typed `ctx` dict** — handlers assume specific keys exist in `ctx` and crash if missing; replace the plain `dict` with a `TypedDict` or dataclass so key errors are caught by type checkers

## Bigger ideas

- ✅ **Persistent node registry** — store seen nodes in the DB, track last-seen time, build a `/whois !abc123` command
- **Repeater/relay mode** — forward messages between channels or to a webhook (Slack, Discord, Telegram)
- **APRS bridge** — Meshtastic positions → APRS-IS, so nodes show up on aprs.fi
- **Web UI enhancements** — live updates via SSE/WebSocket, map view of node positions using Leaflet.js
- **Keyset pagination** — replace `OFFSET`-based paging in `db.py` with cursor-based keyset pagination for performance on large message tables
- **Structured logging** — JSON log output (e.g. via `structlog`) for easier ops monitoring and log aggregation
- **Dependency audit in CI** — add `pip-audit` step to `.github/workflows/ci.yml` to catch known vulnerabilities in dependencies
- **Config reload on SIGHUP** — reload `config.yaml` without restarting the bot, useful for changing county or rate limits in production
