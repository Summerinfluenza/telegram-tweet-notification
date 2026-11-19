#!/usr/bin/env bash
# Installs (or updates) the notifier on a Debian/Ubuntu server with systemd.
# Run as root from the repo checkout at /opt/telegram-tweet-notification:
#   sudo ./deploy/install.sh
# Safe to run again after `git pull`.
set -euo pipefail

APP_NAME="telegram-tweet-notification"
APP_DIR="/opt/${APP_NAME}"
APP_USER="tweetbot"
ENV_FILE="/etc/${APP_NAME}.env"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if [[ "$REPO_DIR" != "$APP_DIR" ]]; then
  echo "Clone the repo to ${APP_DIR} first (found it at ${REPO_DIR})." >&2
  exit 1
fi

echo "==> System packages"
if ! python3 -m venv --help >/dev/null 2>&1; then
  apt-get update -q
  apt-get install -y -q python3-venv
fi

echo "==> Service user '${APP_USER}'"
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
fi

echo "==> Python environment"
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install -q --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt"

echo "==> Secrets file ${ENV_FILE}"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "${APP_DIR}/.env.example" "$ENV_FILE"
  echo "    Created from template. Fill it in before the bot can work."
fi
chown "root:${APP_USER}" "$ENV_FILE"
chmod 640 "$ENV_FILE"

echo "==> systemd units"
cp "${APP_DIR}/deploy/${APP_NAME}.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/${APP_NAME}.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "${APP_NAME}.timer"

echo
echo "Done. Next:"
echo "  1. sudo nano ${ENV_FILE}        (replace every REPLACE_ME)"
echo "  2. sudo systemctl start ${APP_NAME}.service   (test run)"
echo "  3. journalctl -u ${APP_NAME} -n 20            (see the result)"
