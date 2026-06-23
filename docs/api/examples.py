#!/usr/bin/env python3
"""
examples.py — Python examples for the MeshtasticBot REST API

Usage:
    python3 docs/api/examples.py

Override defaults via environment variables:
    BASE_URL=http://myserver:8080 ADMIN_USER=admin ADMIN_PASS=secret python3 docs/api/examples.py
"""

import os
import sys

import requests
from requests.auth import HTTPBasicAuth

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
AUTH = HTTPBasicAuth(
    os.getenv("ADMIN_USER", "admin"),
    os.getenv("ADMIN_PASS", "changeme"),
)


def run_command(command: str, lat: float | None = None, lon: float | None = None) -> list[str]:
    """Execute a bot command via the REST API and return the list of reply strings."""
    payload: dict = {"command": command}
    if lat is not None and lon is not None:
        payload["lat"] = lat
        payload["lon"] = lon

    resp = requests.post(f"{BASE_URL}/api/command", json=payload, auth=AUTH, timeout=30)
    resp.raise_for_status()
    return resp.json()["replies"]


def print_replies(title: str, replies: list[str]) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")
    for reply in replies:
        print(reply)


def main():
    # ── Basic commands ────────────────────────────────────────────────────────

    print_replies("Ping / uptime", run_command("/ping"))
    print_replies("Help", run_command("/help"))
    print_replies("Node list", run_command("/nodes"))

    # ── Weather (Kristiansand) ────────────────────────────────────────────────

    lat, lon = 58.1467, 7.9956
    print_replies("7-day forecast (Kristiansand)", run_command("/weather", lat, lon))
    print_replies("24-hour forecast (Kristiansand)", run_command("/24hour", lat, lon))

    # ── Alerts ────────────────────────────────────────────────────────────────

    print_replies("Active weather alerts", run_command("/alert"))

    # ── Radio ─────────────────────────────────────────────────────────────────

    print_replies("HF/VHF band conditions", run_command("/radio"))
    print_replies("Band plan — 20m", run_command("/bandplan 20m"))
    print_replies("Frequency lookup 14.225 MHz", run_command("/bandplan_check 14.225"))
    print_replies("Calling frequencies — 2m", run_command("/calling 2m"))
    print_replies("Marine VHF channel 16", run_command("/mvhf 16"))

    # ── Log queries ───────────────────────────────────────────────────────────

    print_replies("Last 10 messages", run_command("/krslast 10"))
    print_replies("Log — last 6 hours", run_command("/krslog 6"))

    # ── Error handling examples ───────────────────────────────────────────────

    print(f"\n{'─' * 60}")
    print("  Error handling")
    print(f"{'─' * 60}")

    # Wrong credentials → 401
    resp = requests.post(
        f"{BASE_URL}/api/command",
        json={"command": "/ping"},
        auth=HTTPBasicAuth("admin", "wrongpassword"),
        timeout=10,
    )
    print(f"/ping with wrong password → HTTP {resp.status_code}")

    # Unknown command → 400
    resp = requests.post(
        f"{BASE_URL}/api/command",
        json={"command": "/doesnotexist"},
        auth=AUTH,
        timeout=10,
    )
    print(f"/doesnotexist → HTTP {resp.status_code}: {resp.json()['error']}")

    # Weather without coordinates → replies with GPS error
    replies = run_command("/weather")
    print(f"/weather (no coords) → {replies[0]}")


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print(f"Could not connect to {BASE_URL}. Is the bot running?", file=sys.stderr)
        sys.exit(1)
