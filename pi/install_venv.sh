#!/usr/bin/env bash
#
# Create the Python virtual environment for the RF-Nano MQTT hub.
# Run from anywhere:   bash install_venv.sh
#
# Creates ./venv next to this script and installs requirements.txt into it.
# The systemd service runs  <this dir>/venv/bin/python -m mqtt_hub.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${HERE}/venv"
REQ="${HERE}/requirements.txt"

echo "==> Creating virtualenv at ${VENV}"
python3 -m venv "${VENV}"

echo "==> Upgrading pip"
"${VENV}/bin/python" -m pip install --upgrade pip >/dev/null

echo "==> Installing requirements"
"${VENV}/bin/python" -m pip install -r "${REQ}"

echo
echo "Done. Quick test:"
echo "  cd ${HERE} && ./venv/bin/python -m mqtt_hub --help"
