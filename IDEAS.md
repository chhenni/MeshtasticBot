# Ideas & Future Work

## Small / quick wins

- ✅ **`/ping`** — bot replies with uptime and node count, useful for checking the mesh is alive
- ✅ **`/nodes`** — list currently seen nodes on the mesh with signal strength (RSSI/SNR)
- ✅ **Rate limiting** — ignore repeated commands from the same sender within N seconds to prevent spam
- ✅ **Config validation** — fail fast at startup with a clear error if `config.yaml` is missing required fields
- ✅ **GitHub Actions CI** — run the test suite automatically on push
- ✅ **Environment variable config overrides** — any `MESHTASTIC__SECTION__KEY` env var overlays `config.yaml` at startup; type is inferred from the YAML value so no hardcoded mapping is needed

## Open items

Open items are now tracked as GitHub Issues: https://github.com/chhenni/MeshtasticBot/issues

| # | Title | Label |
|---|---|---|
| [#1](https://github.com/chhenni/MeshtasticBot/issues/1) | `/tide` — Norwegian tide tables | enhancement |
| [#2](https://github.com/chhenni/MeshtasticBot/issues/2) | Per-command rate limiting | enhancement |
| [#3](https://github.com/chhenni/MeshtasticBot/issues/3) | Web UI authentication for public pages | web-ui |
| [#4](https://github.com/chhenni/MeshtasticBot/issues/4) | Config validation improvements | ops |
| [#5](https://github.com/chhenni/MeshtasticBot/issues/5) | `/health` JSON endpoint | ops, web-ui |
| [#6](https://github.com/chhenni/MeshtasticBot/issues/6) | Web route tests | testing |
| [#7](https://github.com/chhenni/MeshtasticBot/issues/7) | Graceful shutdown | reliability |
| [#8](https://github.com/chhenni/MeshtasticBot/issues/8) | Typed ctx dict | reliability |
| [#9](https://github.com/chhenni/MeshtasticBot/issues/9) | Repeater / relay mode | big-idea |
| [#10](https://github.com/chhenni/MeshtasticBot/issues/10) | APRS bridge | big-idea |
| [#11](https://github.com/chhenni/MeshtasticBot/issues/11) | Web UI enhancements: live updates and map view | big-idea, web-ui |
| [#12](https://github.com/chhenni/MeshtasticBot/issues/12) | Keyset pagination for message log | reliability |
| [#13](https://github.com/chhenni/MeshtasticBot/issues/13) | Structured logging with structlog | ops |
| [#14](https://github.com/chhenni/MeshtasticBot/issues/14) | Config reload on SIGHUP | ops |
