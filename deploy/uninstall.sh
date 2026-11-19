#!/usr/bin/env bash
# Stops and removes the notifier from the server.
#   sudo ./deploy/uninstall.sh
# Keeps your settings and the code; pass --purge to delete those too.
set -euo pipefail

APP_NAME="telegram-tweet-notification"

[[ $EUID -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }

systemctl disable --now "${APP_NAME}.timer" 2>/dev/null || true
rm -f "/etc/systemd/system/${APP_NAME}.service" "/etc/systemd/system/${APP_NAME}.timer"
systemctl daemon-reload
rm -rf "/var/lib/${APP_NAME}"
echo "Timer removed and state deleted."

if [[ "${1:-}" == "--purge" ]]; then
  rm -f "/etc/${APP_NAME}.env"
  userdel tweetbot 2>/dev/null || true
  rm -rf "/opt/${APP_NAME}"
  echo "Settings, user and code deleted."
else
  echo "Kept /etc/${APP_NAME}.env and /opt/${APP_NAME} (use --purge to delete)."
fi
