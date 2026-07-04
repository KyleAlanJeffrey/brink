#!/usr/bin/env bash
#
# Install the RF-Nano -> Home Assistant MQTT bridge as a systemd service.
# Run with sudo:   sudo bash install_service.sh
#
set -euo pipefail

SERVICE="rfnano-bridge"
UNIT="/etc/systemd/system/${SERVICE}.service"
ENVFILE="/etc/${SERVICE}.env"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root:  sudo bash install_service.sh" >&2
  exit 1
fi

# User that will own/run the service (the human who ran sudo, not root).
RUN_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"

# service/ dir is this script's dir; the Python scripts live one level up.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$(cd "${HERE}/.." && pwd)"

echo "Installing '${SERVICE}'"
echo "  run as user : ${RUN_USER}"
echo "  scripts in  : ${SCRIPT_DIR}"

# 1. Python dependencies (prefer distro packages; fall back to pip).
echo "==> Installing Python dependencies"
if apt-get update -qq && apt-get install -y python3-serial python3-paho-mqtt >/dev/null 2>&1; then
  echo "    installed via apt"
else
  echo "    apt packages unavailable, using pip"
  python3 -m pip install --break-system-packages pyserial paho-mqtt
fi

# 2. Serial port access for the run user.
echo "==> Adding ${RUN_USER} to the 'dialout' group (serial access)"
usermod -aG dialout "${RUN_USER}" || true

# 3. Environment file with broker details (never overwrite an existing one).
if [[ -f "${ENVFILE}" ]]; then
  echo "==> ${ENVFILE} already exists, leaving it untouched"
else
  echo "==> Creating ${ENVFILE} (edit it with your broker details)"
  install -m 600 "${HERE}/rfnano-bridge.env.example" "${ENVFILE}"
fi

# 4. Render the unit file with the real user + path.
echo "==> Writing ${UNIT}"
sed -e "s|@USER@|${RUN_USER}|g" -e "s|@DIR@|${SCRIPT_DIR}|g" \
    "${HERE}/rfnano-bridge.service" > "${UNIT}"

# 5. Enable (but don't start until the env file is filled in).
echo "==> Enabling service"
systemctl daemon-reload
systemctl enable "${SERVICE}" >/dev/null

cat <<EOF

Done. Next steps:
  1. Enter your broker details:   sudo nano ${ENVFILE}
  2. Start the service:           sudo systemctl start ${SERVICE}
  3. Follow the logs:             journalctl -u ${SERVICE} -f

Note: if ${RUN_USER} was just added to 'dialout', log out/in (or reboot)
so serial-port access takes effect before starting the service.
EOF
