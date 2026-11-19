#!/usr/bin/env bash
# =====================================================================
#  Auto-update: keeps the server in sync with GitHub.
#
#  Runs every 5 minutes (telegram-tweet-notification-update.timer):
#    1. Is there a new commit on GitHub (branch main)?
#    2. Did the GitHub tests pass for it? Wait if still running,
#       skip it if they failed.
#    3. Update the code, install new packages if needed.
#    4. Quick self-test. If it fails: roll back to the previous version.
#    5. Apply changed systemd timer/service files.
#    6. Tell you in Telegram what happened.
#
#  Security: install.sh copies this script to /usr/local/sbin, so a push
#  to GitHub can never change what runs as root. Changes to this file or
#  to install.sh only take effect after you run install.sh by hand.
#  The bot itself always runs as the unprivileged tweetbot user.
# =====================================================================
set -euo pipefail

# Paths can be overridden for testing; normal installs use the defaults.
APP_NAME="telegram-tweet-notification"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
APP_USER="${APP_USER:-tweetbot}"
ENV_FILE="${ENV_FILE:-/etc/${APP_NAME}.env}"
STATE_DIR="${STATE_DIR:-/var/lib/${APP_NAME}}"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"
BRANCH="main"
FAILED_MARKER="${STATE_DIR}/update-skipped-commit"

# Optional setting in the env file: AUTO_UPDATE_REQUIRE_TESTS=false to
# deploy without waiting for GitHub tests (needed for private repos).
REQUIRE_TESTS="$(grep -E '^AUTO_UPDATE_REQUIRE_TESTS=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '"'"'"' ' || true)"
REQUIRE_TESTS="${REQUIRE_TESTS:-true}"

PYTHON="${APP_DIR}/.venv/bin/python"

log() { echo "$*"; }

# Run a command as the bot user with the bot's settings loaded.
as_bot() {
  runuser -u "$APP_USER" -- bash -c '
    set -a; source "$1"; set +a
    cd "$2"; shift 2
    exec "$@"
  ' _ "$ENV_FILE" "$APP_DIR" "$@"
}

# Best effort: an update must never fail just because Telegram is down.
notify() {
  as_bot "$PYTHON" -m notifier.main --notify "$1" >/dev/null 2>&1 \
    || log "(could not send Telegram notice)"
}

# Prints success / failure / pending for a commit's GitHub checks.
ci_status() {
  local sha="$1" slug
  slug="$(git -C "$APP_DIR" remote get-url origin | sed -E 's#(\.git)?/?$##; s#^.*github\.com[:/]##')"
  curl -fsS --max-time 20 -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/${slug}/commits/${sha}/check-runs" 2>/dev/null \
    | python3 -c '
import json, sys
runs = json.load(sys.stdin).get("check_runs", [])
if not runs or any(r["status"] != "completed" for r in runs):
    print("pending")
elif all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs):
    print("success")
else:
    print("failure")
' 2>/dev/null || echo "pending"   # GitHub unreachable: just try again later
}

install_packages() {
  "$PYTHON" -m pip install -q -r "${APP_DIR}/requirements.txt"
}

self_test() {
  as_bot "$PYTHON" -c "import notifier.main, notifier.check" >/dev/null 2>&1
}

# ---------------------------------------------------------------- main

cd "$APP_DIR"
git fetch --quiet origin "$BRANCH"

current="$(git rev-parse HEAD)"
latest="$(git rev-parse "origin/${BRANCH}")"
if [[ "$current" == "$latest" ]]; then
  exit 0   # up to date
fi

# A commit that was already skipped (failed tests or broken) stays skipped
# until a newer commit arrives, so you get one notice, not one every 5 min.
if [[ "$(cat "$FAILED_MARKER" 2>/dev/null || true)" == "$latest" ]]; then
  exit 0
fi

short="${latest:0:7}"
subject="$(git log -1 --format=%s "$latest")"

if [[ "$REQUIRE_TESTS" == "true" ]]; then
  status="$(ci_status "$latest")"
  case "$status" in
    pending)
      log "New commit ${short}, waiting for GitHub tests to finish"
      exit 0 ;;
    failure)
      log "Commit ${short} failed its tests, not deploying"
      echo "$latest" > "$FAILED_MARKER"
      notify "⚠️ Not deployed: ${short} \"${subject}\" failed its GitHub tests. The server keeps running the previous version."
      exit 0 ;;
  esac
fi

log "Updating ${current:0:7} -> ${short}: ${subject}"
changed="$(git diff --name-only "$current" "$latest")"
git reset --quiet --hard "$latest"

if grep -qx "requirements.txt" <<<"$changed"; then
  log "requirements.txt changed, installing packages"
  install_packages
fi

if ! self_test; then
  log "Self-test failed, rolling back to ${current:0:7}"
  git reset --quiet --hard "$current"
  echo "$latest" > "$FAILED_MARKER"
  if grep -qx "requirements.txt" <<<"$changed"; then install_packages; fi
  notify "❌ Update to ${short} \"${subject}\" broke the bot, so it was rolled back to ${current:0:7}. Check: journalctl -u ${APP_NAME}-update"
  exit 1
fi

if grep -qE "^deploy/.*\.(service|timer)$" <<<"$changed"; then
  log "systemd files changed, applying"
  cp "${APP_DIR}/deploy/${APP_NAME}.service" "${APP_DIR}/deploy/${APP_NAME}.timer" "$UNIT_DIR/"
  systemctl daemon-reload
  systemctl restart "${APP_NAME}.timer"
fi

note=""
if grep -qE "^deploy/(install|auto-update)\.sh$|^deploy/${APP_NAME}-update\." <<<"$changed"; then
  note=$'\n'"ℹ️ Installer files changed. Run once on the server: sudo ${APP_DIR}/deploy/install.sh"
fi

rm -f "$FAILED_MARKER"
log "Updated to ${short}"
notify "🔄 Bot updated to ${short}: ${subject}${note}"
