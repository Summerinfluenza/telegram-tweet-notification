# telegram-tweet-notification

Get a Telegram message when chosen X (Twitter)
accounts post. Runs free on GitHub Actions
every 5 minutes.

## How it works

1. GitHub Actions starts the script on a schedule.
2. It asks X for posts newer than the last one seen.
3. Each new post is sent to your Telegram chat.
4. The "last seen" ids are kept in the Actions cache.

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
tests/          offline tests (fakes, no network)
.github/workflows/notify.yml   the schedule
```

## Secrets

Add these in the repo under
**Settings → Secrets and variables → Actions →
New repository secret**:

| Name | Value |
|---|---|
| `X_BEARER_TOKEN` | X app bearer token |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your chat id |
| `X_ACCOUNTS` | e.g. `nasa,spacex` |

`X_ACCOUNTS` is a secret so nobody can see
who you follow, even if the repo is public.

Optional **variables** (Variables tab):
`INCLUDE_REPLIES`, `INCLUDE_REPOSTS`
(`true`/`false`, default `false`).

## Telegram setup

1. In Telegram, message **@BotFather** →
   `/newbot` → copy the token.
2. Send any message to your new bot.
3. Open in a browser:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Copy `"chat":{"id": ...}` → that's
   `TELEGRAM_CHAT_ID`.

## Costs

- **X API:** pay-per-use, about $0.005 per post
  returned. Checks with nothing new return
  nothing. Rough guide: an account posting
  10×/day ≈ $1.50/month.
- **GitHub Actions:** free in a **public** repo.
  A private repo gets 2,000 free min/month; every
  5 min uses far more, so change the cron to
  `*/30 * * * *` if you keep it private.
- **Telegram:** free.

## Good to know

- GitHub may run scheduled jobs a few minutes late.
- In public repos GitHub pauses schedules after
  60 days without commits. Re-enable it in the
  Actions tab (or push any commit).
- A failed run (bad token, X down) shows red in
  Actions and GitHub emails you.

## Run locally

```bash
pip install -r requirements-dev.txt
pytest
cp .env.example .env   # fill in real values
set -a; source .env; set +a
python -m notifier.main
```
