#!/usr/bin/env bash
# Run the MeshtasticBot test suite.
# Usage: ./run_tests.sh [pytest args]
#   ./run_tests.sh            — run all tests with verbose output
#   ./run_tests.sh -x         — stop on first failure
#   ./run_tests.sh tests/test_db.py  — run a single file

set -e
cd "$(dirname "$0")"

if [ ! -f .venv/bin/activate ]; then
    echo "No .venv found. Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

source .venv/bin/activate
python -m pytest tests/ -v "$@"
