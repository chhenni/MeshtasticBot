#!/usr/bin/env bash
# Start MeshtasticBot in dummy mode (no device required).
# Usage: ./run_dummy.sh [--channel N] [extra args]
#   ./run_dummy.sh              — use channel from config.yaml
#   ./run_dummy.sh --channel 0  — override channel

cd "$(dirname "$0")"

if [ ! -f .venv/bin/activate ]; then
    echo "No .venv found. Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

source .venv/bin/activate
python src/main.py --dummy "$@"
