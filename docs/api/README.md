# REST API — `/api/command`

Execute any bot command over HTTP. Requires the same Basic Auth credentials as the admin pages (`admin.username` / `admin.password` in `config.yaml`).

## Endpoint

```
POST /api/command
Authorization: Basic <base64(username:password)>
Content-Type: application/json
```

### Request body

| Field | Type | Required | Description |
|---|---|---|---|
| `command` | string | ✅ | Full command string, e.g. `"/ping"` or `"/bandplan 20m"` |
| `lat` | number | Only for `/weather`, `/24hour` | Latitude in decimal degrees |
| `lon` | number | Only for `/weather`, `/24hour` | Longitude in decimal degrees |

### Response `200 OK`

```json
{
  "command": "/ping",
  "replies": [
    "🟢 Pong! Oppe: 2t 15m | Noder sett: 4"
  ]
}
```

`replies` is an array of strings — one element per Meshtastic message page. Long responses (e.g. `/help`, `/weather`) will have multiple elements.

### Error responses

| Status | Condition |
|---|---|
| `401` | Missing or wrong credentials |
| `400` | `{"error": "Missing command"}` |
| `400` | `{"error": "Unknown command: /foo"}` |
| `400` | `{"error": "lat and lon must be numbers"}` |
| `503` | Bot interface not connected |

---

## Examples

### curl

```bash
# Ping
curl -u admin:changeme -X POST http://localhost:8080/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "/ping"}'

# 7-day weather forecast (coordinates required)
curl -u admin:changeme -X POST http://localhost:8080/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "/weather", "lat": 58.1467, "lon": 7.9956}'

# Active weather alerts
curl -u admin:changeme -X POST http://localhost:8080/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "/alert"}'

# Band plan for 20m
curl -u admin:changeme -X POST http://localhost:8080/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "/bandplan 20m"}'

# Last 10 messages from the log
curl -u admin:changeme -X POST http://localhost:8080/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "/krslast 10"}'

# Add a privileged node (admin auth is sufficient)
curl -u admin:changeme -X POST http://localhost:8080/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "/addpriv !aabbccdd"}'
```

### Python

```python
import requests
from requests.auth import HTTPBasicAuth

AUTH = HTTPBasicAuth("admin", "changeme")

def run_command(command, lat=None, lon=None):
    payload = {"command": command}
    if lat is not None and lon is not None:
        payload["lat"] = lat
        payload["lon"] = lon
    resp = requests.post(
        "http://localhost:8080/api/command",
        json=payload,
        auth=AUTH,
    )
    resp.raise_for_status()
    return resp.json()["replies"]

# Examples
print(run_command("/ping"))
print(run_command("/weather", lat=58.1467, lon=7.9956))
print(run_command("/alert"))
print(run_command("/krslast 10"))
```

See [`examples.sh`](examples.sh) and [`examples.py`](examples.py) for runnable scripts covering all commands.

---

## Available commands

All commands from `/help` are available via the API. Privileged commands (`/addpriv`, `/removepriv`, `/awning`) are also accessible — admin auth is treated as sufficient.

| Command | Notes |
|---|---|
| `/ping` | Uptime and node count |
| `/help` | All command descriptions |
| `/nodes` | Mesh nodes currently seen |
| `/weather` | 7-day forecast — requires `lat`/`lon` |
| `/24hour` | 24-hour hourly forecast — requires `lat`/`lon` |
| `/alert` | Active lightning and wind alerts |
| `/radio` | HF/VHF band conditions |
| `/bandplan <band>` | IARU Region 1 band plan, e.g. `20m` |
| `/bandplan_check <freq>` | Frequency lookup, e.g. `14.225` |
| `/calling <band>` | Calling frequencies |
| `/mvhf [channel]` | Marine VHF channels |
| `/whois <id/name>` | Node lookup |
| `/krslog [t]` | Message log for last _t_ hours |
| `/krslast [n]` | Last _n_ messages |
| `/addpriv <node_id>` | Add privileged node _(admin only)_ |
| `/removepriv <node_id>` | Remove privileged node _(admin only)_ |
| `/awning <action>` | Control awning via Flipper Zero _(admin only)_ |
