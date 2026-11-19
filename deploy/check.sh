#!/usr/bin/env bash
# Tests every connection (Telegram, X, IBKR, AI) and sends a sample alert.
# Run on the server after installing or changing settings:
#   sudo /opt/telegram-tweet-notification/deploy/check.sh
set -euo pipefail

APP_DIR="/opt/telegram-tweet-notification"
ENV_FILE="/etc/telegram-tweet-notification.env"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

# Same user and settings as the real timer runs.
exec sudo -u tweetbot bash -c "
  set -a; source '$ENV_FILE'; set +a
  cd '$APP_DIR'
  STATE_FILE=/var/lib/telegram-tweet-notification/state.json \
    exec '$APP_DIR/.venv/bin/python' -m notifier.main --check
"
