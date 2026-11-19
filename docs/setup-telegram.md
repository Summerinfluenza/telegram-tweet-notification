# Telegram setup

You need a **bot token** and your **chat id**.
Both are free and take 2 minutes.

## 1. Create the bot

1. In Telegram, open a chat with **@BotFather**.
2. Send `/newbot`.
3. Pick a name and a username ending in `bot`.
4. BotFather replies with a token like
   `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`.
   That's `TELEGRAM_BOT_TOKEN`.

Keep the token secret: anyone with it can send
messages as your bot.

## 2. Say hi to your bot

Open your new bot in Telegram and press
**Start** (or send any message).

This step matters: bots can't message you first.
Skipping it gives `chat not found`.

## 3. Find your chat id

Open this in a browser, with your token:

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

Find `"chat":{"id":123456789` → that number is
`TELEGRAM_CHAT_ID`.

Empty result (`"result":[]`)? Send the bot another
message and reload.

## 4. Put them in the settings file

```bash
sudo nano /etc/telegram-tweet-notification.env
```

```
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=123456789
```

## Alerts in a group or channel instead

- **Group:** add the bot to the group, send a
  message there, then use `getUpdates`. Group ids
  start with `-` (e.g. `-1001234567890`).
- **Channel:** add the bot as an admin. Use
  `@channelname` or the `-100…` id.

## Test

```bash
sudo /opt/telegram-tweet-notification/deploy/check.sh
```

You should get a sample alert in Telegram.
