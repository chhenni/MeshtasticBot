# Ideas & Future Work

## Small / quick wins

- ✅ **`/ping`** — bot replies with uptime and node count, useful for checking the mesh is alive
- ✅ **`/nodes`** — list currently seen nodes on the mesh with signal strength (RSSI/SNR)
- ✅ **Rate limiting** — ignore repeated commands from the same sender within N seconds to prevent spam
- ✅ **Config validation** — fail fast at startup with a clear error if `config.yaml` is missing required fields

## Medium effort

- **`/tide <location>`** — Norwegian tide tables from `api.sehavniva.no` (free Norwegian government API, same pattern as yr.no)
- ✅ **`/alert`** — on-demand weather alert check, not just the background loop
- **`/krssearch <term>`** — search the log DB by keyword
- **GitHub Actions CI** — run the test suite automatically on push (the multi-stage Dockerfile already does this locally, but a proper CI pipeline adds confidence on PRs)

## Bigger ideas

- ✅ **Persistent node registry** — store seen nodes in the DB, track last-seen time, build a `/whois !abc123` command
- **Repeater/relay mode** — forward messages between channels or to a webhook (Slack, Discord, Telegram)
- **APRS bridge** — Meshtastic positions → APRS-IS, so nodes show up on aprs.fi
- **Web UI enhancements** — live updates via SSE/WebSocket, map view of node positions using Leaflet.js
