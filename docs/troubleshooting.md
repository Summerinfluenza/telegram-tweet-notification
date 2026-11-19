# Troubleshooting

First step, always:

```bash
sudo /opt/telegram-tweet-notification/deploy/check.sh
journalctl -u telegram-tweet-notification -n 50
```

The check tests each part on its own and says
what's wrong.

## No alerts at all

**Is the timer running?**

```bash
systemctl list-timers telegram-tweet-notification
```

No line → `sudo ./deploy/install.sh` again.

**Did the account post since you installed?**
The first run only records where to start. Old
posts are never sent.

**Replies or reposts?** Skipped by default. Set
`INCLUDE_REPLIES=true` / `INCLUDE_REPOSTS=true`.

## Log messages

`Setting problem: …`
A setting is missing or wrong. The message names
it. Fix it in
`/etc/telegram-tweet-notification.env`.

`X rejected the bearer token (401)`
Wrong or regenerated token. Copy a fresh one, see
[setup-x.md](setup-x.md).

`X API credits are used up (402)`
Top up in console.x.com → Billing.

`X refused access (403)`
The app needs to be in a project with billing
enabled.

`X account @name not found`
Typo in `X_ACCOUNTS`, or the account was renamed
or deleted.

`Telegram can't find the chat`
Wrong `TELEGRAM_CHAT_ID`, or you never pressed
Start in your bot's chat.

`Telegram rejected the bot token (401)`
Wrong token. Get it again from @BotFather
(`/mybots` → your bot → API Token).

`Could not connect to IB Gateway`
Gateway not running, logged out, wrong port, or
API not enabled. See [setup-ibkr.md](setup-ibkr.md).

`IBKR returned no prices`
Usually missing market data subscription for API
use.

`AI provider rejected the key`
Wrong `AI_API_KEY`, or no credits left at the
provider.

`AI model '…' not found`
The model was renamed or retired. Set `AI_MODEL`,
see [setup-ai.md](setup-ai.md).

`State file was damaged`
Harmless. The bot moved the old file aside and
started fresh. You may miss posts from the last
few minutes, nothing more.

## Start over from scratch

Forget all "last seen" posts (next run starts
fresh, no old alerts):

```bash
sudo rm /var/lib/telegram-tweet-notification/state.json
```

Full reinstall:

```bash
cd /opt/telegram-tweet-notification
sudo ./deploy/uninstall.sh
sudo ./deploy/install.sh
```

Your settings file is kept.
