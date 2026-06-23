#!/usr/bin/env bash
# examples.sh — curl examples for the MeshtasticBot REST API
#
# Usage:
#   chmod +x docs/api/examples.sh
#   ./docs/api/examples.sh
#
# Override defaults via environment variables:
#   BASE_URL=http://myserver:8080 ADMIN_USER=admin ADMIN_PASS=secret ./docs/api/examples.sh

BASE_URL="${BASE_URL:-http://localhost:8080}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-changeme}"

cmd() {
    local description="$1"; shift
    echo ""
    echo "=== $description ==="
    curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
         -X POST "$BASE_URL/api/command" \
         -H "Content-Type: application/json" \
         "$@" | python3 -m json.tool
}

# ── Basic commands ────────────────────────────────────────────────────────────

cmd "Ping / uptime check" \
    -d '{"command": "/ping"}'

cmd "Help pages" \
    -d '{"command": "/help"}'

cmd "Node list" \
    -d '{"command": "/nodes"}'

# ── Weather (requires lat/lon) ─────────────────────────────────────────────

cmd "7-day forecast for Kristiansand" \
    -d '{"command": "/weather", "lat": 58.1467, "lon": 7.9956}'

cmd "24-hour hourly forecast for Kristiansand" \
    -d '{"command": "/24hour", "lat": 58.1467, "lon": 7.9956}'

# ── Alerts ────────────────────────────────────────────────────────────────────

cmd "Active weather alerts" \
    -d '{"command": "/alert"}'

# ── Radio ─────────────────────────────────────────────────────────────────────

cmd "HF/VHF band conditions" \
    -d '{"command": "/radio"}'

cmd "Band plan for 20m" \
    -d '{"command": "/bandplan 20m"}'

cmd "Frequency lookup: 14.225 MHz" \
    -d '{"command": "/bandplan_check 14.225"}'

cmd "Calling frequencies for 2m" \
    -d '{"command": "/calling 2m"}'

cmd "Marine VHF channel 16" \
    -d '{"command": "/mvhf 16"}'

# ── Log queries ───────────────────────────────────────────────────────────────

cmd "Last 10 messages from the log" \
    -d '{"command": "/krslast 10"}'

cmd "Message log for the last 6 hours" \
    -d '{"command": "/krslog 6"}'

# ── Node lookup ───────────────────────────────────────────────────────────────

cmd "Whois by node ID" \
    -d '{"command": "/whois !aabbccdd"}'

# ── Privileged commands (admin auth is sufficient) ────────────────────────────

cmd "Add a privileged node" \
    -d '{"command": "/addpriv !aabbccdd"}'

cmd "Remove a privileged node" \
    -d '{"command": "/removepriv !aabbccdd"}'

# ── Error cases ───────────────────────────────────────────────────────────────

echo ""
echo "=== Auth failure (expect 401) ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
     -u "admin:wrongpassword" \
     -X POST "$BASE_URL/api/command" \
     -H "Content-Type: application/json" \
     -d '{"command": "/ping"}'

echo ""
echo "=== Unknown command (expect 400) ==="
curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
     -X POST "$BASE_URL/api/command" \
     -H "Content-Type: application/json" \
     -d '{"command": "/doesnotexist"}' | python3 -m json.tool

echo ""
echo "=== Weather without coords (expect GPS error in replies) ==="
curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
     -X POST "$BASE_URL/api/command" \
     -H "Content-Type: application/json" \
     -d '{"command": "/weather"}' | python3 -m json.tool
