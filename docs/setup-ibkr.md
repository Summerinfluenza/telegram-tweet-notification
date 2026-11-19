# IBKR setup

The bot reads QQQ/SPY daily prices from
**IB Gateway** (or TWS) running on the same
server, and calculates:

- last price and change today
- previous day high/low
- 20-day high/low
- 50- and 200-day moving averages

It connects **read-only**: it can't place orders
or see positions.

## Requirements

1. **IB Gateway running and logged in** on the
   server. Most people use **IBC** to keep it
   running and logged in automatically.
2. **API enabled** in IB Gateway:
   *Configure → Settings → API → Settings*
   - Enable ActiveX and Socket Clients: on
   - Read-Only API: on (recommended)
   - Socket port: note it (see below)
   - Trusted IPs: `127.0.0.1`
3. **US stock market data** on the account. API
   requests need a subscription (check *Account
   → Settings → Market Data Subscriptions* in
   Client Portal). If your existing IBKR scripts
   already get prices, you're set.

## Settings

```
IBKR_ENABLED=true
IBKR_HOST=127.0.0.1
IBKR_PORT=4001
IBKR_CLIENT_ID=77
MARKET_SYMBOLS=QQQ,SPY
```

Ports:

- IB Gateway live: `4001`
- IB Gateway paper: `4002`
- TWS live: `7496`
- TWS paper: `7497`

`IBKR_CLIENT_ID` must be different from the ids
your other IBKR scripts use (e.g. a trading bot),
or one will kick the other off.

`MARKET_SYMBOLS` sets which ETFs every alert
analyzes. Add e.g. `IWM` if you want.

## Test

```bash
sudo /opt/telegram-tweet-notification/deploy/check.sh
```

Look for `✅ IBKR prices: QQQ …, SPY …`.

## Gateway on another machine

Set `IBKR_HOST` to its IP, add this server's IP to
*Trusted IPs*, and only allow that port through
the firewall from this server. Never expose the
API port to the internet.

## When the gateway is down

IB Gateway restarts daily and needs a new login
about weekly. While it's down, alerts still go out
with the analysis but without levels, plus
`⚠️ IBKR prices unavailable`.

Don't want IBKR at all? Set `IBKR_ENABLED=false`.
