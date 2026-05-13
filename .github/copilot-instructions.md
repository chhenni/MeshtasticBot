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
- Replies are sent with `interface.sendText(text, channelIndex=<n>)`.
- **Bot logic lives entirely in `generate_reply(text, sender_id)`** — return a string to reply or `None` to stay silent.
- Connection type (serial / tcp / ble) is selected in `config.yaml` and resolved in the `connect()` function.
- The `api.met.no` weather alerts endpoint: `https://api.met.no/weatherapi/metalerts/2.0/all.json?county=<fylkesnummer>`
