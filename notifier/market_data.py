"""QQQ/SPY price levels from Interactive Brokers (IB Gateway / TWS).

The levels are calculated here in code, not by the AI, so the numbers
in a message are always real prices, never invented ones.

Needs IB Gateway (or TWS) running and logged in, with the API enabled
and market data for US stocks on the account. See docs/setup-ibkr.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Sequence

from notifier.config import IbkrSettings

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 10
HISTORY_TIMEOUT_SECONDS = 30


class MarketDataError(Exception):
    """Prices could not be fetched. The message explains why."""


@dataclass(frozen=True)
class DailyBar:
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Levels:
    symbol: str
    last: float
    change_pct: float          # vs previous session close
    prev_high: float           # previous session
    prev_low: float
    high_20d: float            # last 20 sessions, incl. today
    low_20d: float
    sma_50: float | None       # None if not enough history
    sma_200: float | None


def _sma(closes: Sequence[float], length: int) -> float | None:
    if len(closes) < length:
        return None
    return sum(closes[-length:]) / length


def compute_levels(symbol: str, bars: Sequence[DailyBar]) -> Levels:
    """Turn daily bars (oldest first, last = latest session) into levels."""
    if len(bars) < 2:
        raise MarketDataError(f"Not enough price history for {symbol} ({len(bars)} bars).")
    latest, previous = bars[-1], bars[-2]
    window = bars[-20:]
    closes = [bar.close for bar in bars]
    return Levels(
        symbol=symbol,
        last=latest.close,
        change_pct=(latest.close / previous.close - 1) * 100,
        prev_high=previous.high,
        prev_low=previous.low,
        high_20d=max(bar.high for bar in window),
        low_20d=min(bar.low for bar in window),
        sma_50=_sma(closes, 50),
        sma_200=_sma(closes, 200),
    )


def _default_ib_factory():
    # Imported here so the rest of the bot (and the tests) work without it.
    from ib_async import IB

    return IB()


class IbkrMarketData:
    def __init__(self, settings: IbkrSettings, ib_factory: Callable[[], object] = _default_ib_factory):
        self._settings = settings
        self._ib_factory = ib_factory

    def fetch_levels(self, symbols: Sequence[str]) -> dict[str, Levels]:
        from ib_async import Stock
        from ib_async.ib import StartupFetch

        ib = self._ib_factory()
        try:
            try:
                ib.connect(
                    self._settings.host,
                    self._settings.port,
                    clientId=self._settings.client_id,
                    timeout=CONNECT_TIMEOUT_SECONDS,
                    readonly=True,
                    fetchFields=StartupFetch(0),  # skip positions/orders: faster
                )
            except Exception as error:
                raise MarketDataError(
                    f"Could not connect to IB Gateway at {self._settings.host}:{self._settings.port} "
                    f"({error.__class__.__name__}). Is it running and logged in? See docs/setup-ibkr.md."
                ) from error

            levels: dict[str, Levels] = {}
            for symbol in symbols:
                contract = Stock(symbol, "SMART", "USD")
                ib.qualifyContracts(contract)
                raw_bars = ib.reqHistoricalData(
                    contract,
                    endDateTime="",
                    durationStr="1 Y",
                    barSizeSetting="1 day",
                    whatToShow="TRADES",
                    useRTH=True,
                    timeout=HISTORY_TIMEOUT_SECONDS,
                )
                if not raw_bars:
                    raise MarketDataError(
                        f"IBKR returned no prices for {symbol}. "
                        "Does the account have US market data? See docs/setup-ibkr.md."
                    )
                bars = [DailyBar(high=b.high, low=b.low, close=b.close) for b in raw_bars]
                levels[symbol] = compute_levels(symbol, bars)
            return levels
        finally:
            if ib.isConnected():
                ib.disconnect()
