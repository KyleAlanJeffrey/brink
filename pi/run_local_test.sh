#!/usr/bin/env bash
#
# Local test harness: run a Mosquitto broker AND the mqtt_hub bridge, both on
# this Pi, with no network config. Good for confirming the bridge publishes
# correctly before a real broker exists.
#
# Usage:   bash run_local_test.sh [extra mqtt_hub args...]
#   e.g.   bash run_local_test.sh --port /dev/ttyUSB0
#
# In a second terminal, watch the topics with:
#   mosquitto_sub -h localhost -t '#' -v
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${HERE}/venv"

# 1. Virtualenv
if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "==> venv missing, creating it"
  bash "${HERE}/install_venv.sh"
fi

# 2. Broker (install if needed, then make sure it's running)
if ! command -v mosquitto >/dev/null 2>&1; then
  echo "==> installing mosquitto"
  sudo apt-get update -qq
  sudo apt-get install -y mosquitto mosquitto-clients
fi
echo "==> ensuring mosquitto is running on localhost:1883"
sudo systemctl enable --now mosquitto

# 3. Bridge (localhost is the default --mqtt-host; extra args pass through)
echo "==> starting mqtt_hub bridge (Ctrl-C to stop)"
echo "    watch it with:  mosquitto_sub -h localhost -t '#' -v"
exec "${VENV}/bin/python" -m mqtt_hub "$@"
