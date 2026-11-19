# telegram-tweet-notification

Trading alerts in Telegram when chosen X (Twitter)
accounts post. Each alert has:

- 📝 an AI **summary** of the post
- 🟢/🔴 a **bull or bear read on QQQ and SPY**,
  with real price levels from IBKR
- 🏷 the **stocks mentioned**, each with a bias
- 🔗 a link to the original post

Runs on your own Linux server (e.g. Hetzner),
checking every 5 minutes.

## Example alert

```
🐦 @federalreserve
📝 Powell hints at two more cuts as inflation cools.

🟢 QQQ 512.30 (+0.42%) · Bullish
Rate-sensitive tech gains; room up to 20d high 520.
Prev day 505.10–514.20 · 20d 498.00–520.00
· 50d 505.00 · 200d 470.12

🟢 SPY 598.10 (+0.31%) · Bullish
Broad lift; holding above 600.50 is key.
Prev day 594.20–600.50 · 20d 585.30–604.00
· 50d 590.40 · 200d 560.00

🏷 $NVDA 🟢 Cheaper money supports AI capex.
🏷 $AAPL ⚪ Mentioned in passing.

💬 "Fed: two more cuts likely in 2027 as …"
🔗 Open on X
```

Price levels are calculated from IBKR data in
code. The AI only interprets them; it is told
never to invent numbers.

---

## Contents

1. [What you need](#what-you-need)
2. [Install (15 minutes)](#install)
3. [Daily use](#daily-use)
4. [Costs](#costs)
5. [How it works](#how-it-works)
6. [Project layout](#project-layout)
7. [Development](#development)

Detailed guides:

- [X API setup](docs/setup-x.md)
- [Telegram setup](docs/setup-telegram.md)
- [AI provider setup](docs/setup-ai.md)
- [IBKR setup](docs/setup-ibkr.md)
- [Troubleshooting](docs/troubleshooting.md)

---

## What you need

- A Linux server with systemd and Python 3.10+
  (Ubuntu 22.04+ or Debian 12+)
- An **X developer account** with credits
  → [docs/setup-x.md](docs/setup-x.md)
- A **Telegram bot**
  → [docs/setup-telegram.md](docs/setup-telegram.md)
- Optional: an **AI API key** (DeepSeek, Gemini
  or OpenAI) → [docs/setup-ai.md](docs/setup-ai.md)
- Optional: **IB Gateway** running on the server
  → [docs/setup-ibkr.md](docs/setup-ibkr.md)

Without AI you get the raw post. Without IBKR you
get the analysis without price levels. Both can
be switched on later.

## Install

On the server, as root:

**1. Download**

```bash
git clone https://github.com/Summerinfluenza/telegram-tweet-notification.git \
  /opt/telegram-tweet-notification
```

**2. Install**

```bash
cd /opt/telegram-tweet-notification
sudo ./deploy/install.sh
```

This creates a locked-down `tweetbot` user, a
Python environment, the settings file and the
timer. Safe to run again.

**3. Fill in your settings**

```bash
sudo nano /etc/telegram-tweet-notification.env
```

Replace every `REPLACE_ME`. Each line has a
comment explaining it. Save: Ctrl+O, Enter.
Exit: Ctrl+X.

**4. Test**

```bash
sudo /opt/telegram-tweet-notification/deploy/check.sh
```

You should see:

```
✅ Settings file: loaded
✅ Telegram bot: @your_bot
✅ X API: token works, found @nasa
✅ IBKR prices: QQQ 512.30, SPY 598.10
✅ AI analysis: deepseek / deepseek-v4-flash → QQQ bullish, SPY bullish
✅ Telegram message: sample message sent
```

…and a sample alert in Telegram. Any ❌ line says
what to fix. See also
[troubleshooting](docs/troubleshooting.md).

**Done.** The first real run only notes where to
start, so you get alerts for posts made from now
on, not old ones.

## Daily use

All commands run on the server.

See what the bot did:

```bash
journalctl -u telegram-tweet-notification -n 30
```

Follow the log live:

```bash
journalctl -u telegram-tweet-notification -f
```

Run once right now (instead of waiting):

```bash
sudo systemctl start telegram-tweet-notification
```

Pause / resume alerts:

```bash
sudo systemctl stop telegram-tweet-notification.timer
sudo systemctl start telegram-tweet-notification.timer
```

Change settings (accounts, AI provider, …):
edit the settings file. Changes apply on the next
run; no restart needed. Then run `check.sh` again.

Update to the latest code:

```bash
cd /opt/telegram-tweet-notification
sudo git pull
sudo ./deploy/install.sh
```

Check every minute instead of every 5: in
`deploy/telegram-tweet-notification.timer` change
`OnCalendar=*:0/5` to `OnCalendar=minutely`, then
run `install.sh` again. Costs stay the same (see
below).

Remove everything:

```bash
sudo ./deploy/uninstall.sh --purge
```

## Costs

Example: one account posting 10 times a day
(≈300 posts/month).

- **X API:** ≈ $1.50/month
  ($0.005 per post returned; checks that find
  nothing are free, so check frequency doesn't
  matter)
- **AI:** ≈ $0.05–0.10/month
  (DeepSeek or OpenAI mini models; Gemini's free
  tier usually covers it)
- **IBKR:** no extra cost if you already have US
  market data
- **Telegram:** free

≈ **$1.60/month per account** at 10 posts/day.
X gives $20 free credits when you add a card.

## How it works

Every 5 minutes systemd runs the script once:

1. Ask X for posts newer than the last one seen,
   per account.
2. Nothing new? Stop. (Costs nothing.)
3. Fetch QQQ/SPY daily bars from IBKR once and
   calculate levels: last price, day change,
   previous day range, 20-day range, 50/200-day
   averages.
4. For each new post, oldest first: send post +
   levels to the AI, get back summary, biases
   and tickers.
5. Send the alert to Telegram.
6. Remember the last post sent.

Built to never lose or repeat an alert:

- A post counts as sent only after Telegram
  accepts it. If Telegram is down, it's sent next
  run, in the right order.
- If IBKR or the AI fails, the alert still goes
  out, with a ⚠️ note.
- Network errors and rate limits are retried
  automatically.
- One broken account doesn't block the others.
- The state file is written safely; if it's ever
  damaged, the bot starts fresh instead of
  crashing.
- Settings are checked at start; a typo gives a
  clear message, not a crash.

## Project layout

```
notifier/
  main.py         one run, step by step
  check.py        the --check setup test
  config.py       reads + validates settings
  x_client.py     X API
  market_data.py  IBKR prices -> levels
  analysis.py     AI prompt + reply parsing
  messages.py     Telegram message layout
  telegram.py     Telegram API
  state.py        last seen post per account
  http_retry.py   shared retry logic
deploy/
  install.sh      install / update
  check.sh        test all connections
  uninstall.sh    remove
  *.service       what systemd runs
  *.timer         how often
docs/             setup guides
tests/            offline tests, no network
```

Each file does one thing and starts with a short
explanation. Outside services (X, Telegram, AI,
IBKR) are only touched in their own file, so
they're easy to swap or fake in tests.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Tests use fakes for every outside service and
never touch the network. GitHub runs them on every
push (Python 3.10–3.13).

To change the AI's instructions, edit
`SYSTEM_PROMPT` in `notifier/analysis.py`. To
change the alert layout, edit
`notifier/messages.py`.

Run locally against real services:

```bash
cp .env.example .env    # fill in real values
set -a; . ./.env; set +a
python -m notifier.main --check
```

---

The AI analysis is generated automatically and
can be wrong. It's input for your own decisions,
not financial advice.
