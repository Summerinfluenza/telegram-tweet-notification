# telegram-tweet-notification

Get a Telegram message when chosen X (Twitter)
accounts post. Runs on your own Linux server
(systemd), checking every minute.

## How it works

1. A systemd timer starts the script every minute.
2. It asks X for posts newer than the last one seen.
3. Each new post is sent to your Telegram chat.
4. "Last seen" ids are saved in
   `/var/lib/telegram-tweet-notification/state.json`.

The first run for an account only records where
to start, so you don't get old posts.

## Project layout

```
notifier/
  config.py     settings from env vars
  state.py      last-seen post per account
  x_client.py   X API calls
  telegram.py   Telegram messages
  main.py       ties it together
deploy/
  install.sh    one-command server setup
  *.service     what to run
  *.timer       how often
tests/          offline tests (fakes, no network)
.github/workflows/tests.yml   runs tests on push
```

## Install on the server

Debian/Ubuntu with systemd (e.g. Hetzner):

```bash
sudo git clone https://github.com/<you>/telegram-tweet-notification.git \
  /opt/telegram-tweet-notification
cd /opt/telegram-tweet-notification
sudo ./deploy/install.sh
sudo nano /etc/telegram-tweet-notification.env
```

The install script:
- creates a locked-down `tweetbot` user
- sets up a Python venv
- creates the secrets file (readable only by
  root and `tweetbot`)
- enables the timer

## Secrets

Edit `/etc/telegram-tweet-notification.env`:

| Name | Value |
|---|---|
| `X_BEARER_TOKEN` | X app bearer token |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your chat id |
| `X_ACCOUNTS` | e.g. `nasa,spacex` |

Optional: `INCLUDE_REPLIES`, `INCLUDE_REPOSTS`
(`true`/`false`, default `false`).

The file is read on every run, so changes take
effect within a minute. No restart needed.

## Telegram setup

1. In Telegram, message **@BotFather** →
   `/newbot` → copy the token.
2. Send any message to your new bot.
3. Open in a browser:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Copy `"chat":{"id": ...}` → that's
   `TELEGRAM_CHAT_ID`.

## Everyday commands

```bash
# test run now
sudo systemctl start telegram-tweet-notification

# recent log
journalctl -u telegram-tweet-notification -n 30

# live log
journalctl -u telegram-tweet-notification -f

# next scheduled run
systemctl list-timers telegram-tweet-notification

# pause / resume
sudo systemctl stop telegram-tweet-notification.timer
sudo systemctl start telegram-tweet-notification.timer
```

## Update

```bash
cd /opt/telegram-tweet-notification
sudo git pull
sudo ./deploy/install.sh
```

## Change how often it checks

Edit `OnCalendar=` in
`deploy/telegram-tweet-notification.timer`
(e.g. `*:0/5` = every 5 min), then run
`install.sh` again.

## Costs

- **X API:** pay-per-use, about $0.005 per post
  returned. Checks with nothing new return
  nothing, so checking every minute costs the
  same as every hour. Rough guide: an account
  posting 10×/day ≈ $1.50/month.
- **Telegram:** free.

## Run locally

```bash
pip install -r requirements-dev.txt
pytest
cp .env.example .env   # fill in real values
set -a; source .env; set +a
python -m notifier.main
```
