#!/usr/bin/env bash
# Installs (or updates) the notifier on a Debian/Ubuntu server with systemd.
#
# Run as root from the repo checkout at /opt/telegram-tweet-notification:
#   sudo ./deploy/install.sh
#
# Safe to run again any time, e.g. after `git pull`. It never overwrites
# your settings file.
set -euo pipefail

APP_NAME="telegram-tweet-notification"
APP_DIR="/opt/${APP_NAME}"
APP_USER="tweetbot"
ENV_FILE="/etc/${APP_NAME}.env"
STATE_DIR="/var/lib/${APP_NAME}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

say()  { echo -e "\n==> $*"; }
fail() { echo -e "\nERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Run as root: sudo $0"
[[ "$REPO_DIR" == "$APP_DIR" ]] || fail "Clone the repo to ${APP_DIR} first (it is at ${REPO_DIR})."
command -v systemctl >/dev/null || fail "systemd is required (Debian/Ubuntu)."

say "Checking Python"
command -v python3 >/dev/null || { apt-get update -q && apt-get install -y -q python3; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
  || fail "Python 3.10+ is required (found $(python3 --version)). Use Ubuntu 22.04+ or Debian 12+."
if ! python3 -m venv --help >/dev/null 2>&1 || ! python3 -c 'import ensurepip' 2>/dev/null; then
  apt-get update -q
  apt-get install -y -q python3-venv
fi

say "Service user '${APP_USER}'"
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
  echo "    created"
else
  echo "    already exists"
fi

say "Python packages"
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install -q --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt"
echo "    installed"

say "Settings file ${ENV_FILE}"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "${APP_DIR}/.env.example" "$ENV_FILE"
  echo "    created from template - you need to fill it in"
else
  echo "    kept your existing settings"
fi
chown "root:${APP_USER}" "$ENV_FILE"
chmod 640 "$ENV_FILE"

say "State folder ${STATE_DIR}"
mkdir -p "$STATE_DIR"
chown "${APP_USER}:${APP_USER}" "$STATE_DIR"
chmod 750 "$STATE_DIR"

say "systemd timer"
cp "${APP_DIR}/deploy/${APP_NAME}.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/${APP_NAME}.timer" /etc/systemd/system/
chmod +x "${APP_DIR}/deploy/"*.sh
systemctl daemon-reload
systemctl enable --now "${APP_NAME}.timer" >/dev/null
echo "    enabled, next run: $(systemctl show -p NextElapseUSecRealtime --value ${APP_NAME}.timer)"

echo
if grep -q "REPLACE_ME" "$ENV_FILE"; then
  echo "Almost done! Next:"
  echo "  1. sudo nano ${ENV_FILE}     (replace every REPLACE_ME)"
  echo "  2. sudo ${APP_DIR}/deploy/check.sh"
  echo
  echo "Until then the timer runs but logs 'Setting problem' and sends nothing."
else
  echo "Done. Test everything with:"
  echo "  sudo ${APP_DIR}/deploy/check.sh"
fi
