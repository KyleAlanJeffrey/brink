#!/usr/bin/env bash
#
# Install the RF-Nano -> Home Assistant MQTT bridge as a systemd service.
# Run with sudo:   sudo bash install_service.sh
#
# By default this also sets up a local Mosquitto broker on the Pi (reachable on
# the LAN so a separate Home Assistant box can connect). Skip that with:
#   sudo bash install_service.sh --no-broker
#
set -euo pipefail

SERVICE="rfnano-bridge"
UNIT="/etc/systemd/system/${SERVICE}.service"
ENVFILE="/etc/${SERVICE}.env"

SETUP_BROKER=1
for arg in "$@"; do
  [[ "${arg}" == "--no-broker" ]] && SETUP_BROKER=0
done

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root:  sudo bash install_service.sh" >&2
  exit 1
fi

# User that will own/run the service (the human who ran sudo, not root).
RUN_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"

# service/ dir is this script's dir; the package + venv live one level up (pi/).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${HERE}/.." && pwd)"

echo "Installing '${SERVICE}'"
echo "  run as user : ${RUN_USER}"
echo "  project dir : ${PROJECT_DIR}"

# 1. Virtualenv (created as the run user so it owns the files).
echo "==> Creating virtualenv + installing requirements"
sudo -u "${RUN_USER}" bash "${PROJECT_DIR}/install_venv.sh"

# 2. Local MQTT broker (Pi-as-broker). Skip with --no-broker.
if [[ "${SETUP_BROKER}" -eq 1 ]]; then
  echo "==> Setting up local Mosquitto broker"
  if ! command -v mosquitto >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y mosquitto mosquitto-clients >/dev/null
  fi
  install -m 644 "${PROJECT_DIR}/mosquitto/local.conf" \
      /etc/mosquitto/conf.d/local.conf
  systemctl enable --now mosquitto
  systemctl restart mosquitto
  echo "    broker listening on 0.0.0.0:1883 (anonymous; see local.conf to add auth)"
else
  echo "==> Skipping broker setup (--no-broker)"
fi

# 3. Serial port access for the run user.
echo "==> Adding ${RUN_USER} to the 'dialout' group (serial access)"
usermod -aG dialout "${RUN_USER}" || true

# 4. Environment file with broker details (never overwrite an existing one).
if [[ -f "${ENVFILE}" ]]; then
  echo "==> ${ENVFILE} already exists, leaving it untouched"
else
  echo "==> Creating ${ENVFILE} (edit it with your broker details)"
  install -m 600 "${HERE}/rfnano-bridge.env.example" "${ENVFILE}"
fi

# 5. Render the unit file with the real user + path.
echo "==> Writing ${UNIT}"
sed -e "s|@USER@|${RUN_USER}|g" -e "s|@DIR@|${PROJECT_DIR}|g" \
    "${HERE}/rfnano-bridge.service" > "${UNIT}"

# 6. Enable (but don't start until the env file is filled in).
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
