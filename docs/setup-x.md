# X API setup

You need a **bearer token**. It lets the bot read
public posts. It can't post or touch your account.

## 1. Create a developer account

1. Go to **console.x.com** and sign in with your
   normal X account.
2. Accept the developer agreement.
3. Create an **app** (any name, e.g.
   `tweet-notifier`).

## 2. Add credits

The X API is pay-per-use: you buy credits and each
post the bot reads costs about $0.005.

1. In the console, open **Billing → Credits**.
2. Add a payment card. X gives a one-time **$20 in
   free credits** for your first card. At 10
   posts/day that lasts about a year.
3. Set a **spending limit**, so a mistake can
   never run up a bill.

When credits run out, every request fails with
error 402. The bot logs
`X API credits are used up (402)` and sends
nothing until you top up.

## 3. Copy the bearer token

1. Open your app → **Keys and tokens**.
2. Generate the **Bearer Token**.
3. Copy it right away. X shows it only once. If
   lost, regenerate it (the old one stops working).

## 4. Put it in the settings file

```bash
sudo nano /etc/telegram-tweet-notification.env
```

```
X_BEARER_TOKEN=AAAAAAAAAAAAAAAAAAAAA...
X_ACCOUNTS=nasa,spacex
```

- Paste the token as is. A leading `Bearer ` or
  quotes are removed automatically.
- Usernames without `@`, separated by commas.

## 5. Test

```bash
sudo /opt/telegram-tweet-notification/deploy/check.sh
```

Look for `✅ X API: token works`.

Test the token on its own (optional):

```bash
curl "https://api.x.com/2/users/by/username/xdevelopers" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

JSON with an `id` = the token works.

## What costs money

- Reading a post: ≈ $0.005
- Looking up a username: ≈ $0.01, once per account
  (the bot remembers the id)
- A check that finds nothing new: free

Watch your spend live in the console under
**Usage**.
