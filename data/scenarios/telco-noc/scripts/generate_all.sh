#!/usr/bin/env bash
# Generate all data for the telco-noc scenario
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Generating telco-noc scenario data ==="
python3 "$SCRIPT_DIR/generate_topology.py"
python3 "$SCRIPT_DIR/generate_routing.py"
python3 "$SCRIPT_DIR/generate_telemetry.py"
python3 "$SCRIPT_DIR/generate_tickets.py"
echo "=== Done ==="
