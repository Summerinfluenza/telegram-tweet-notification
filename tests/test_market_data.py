from types import SimpleNamespace

import pytest

from notifier.config import IbkrSettings
from notifier.market_data import DailyBar, IbkrMarketData, MarketDataError, compute_levels

SETTINGS = IbkrSettings(enabled=True, host="127.0.0.1", port=4001, client_id=77)


def bars(closes):
    return [DailyBar(high=c + 1, low=c - 1, close=c) for c in closes]


def test_compute_levels_basic_numbers():
    lv = compute_levels("QQQ", bars([100.0] * 18 + [110.0, 99.0]))
    assert lv.last == 99.0
    assert lv.change_pct == pytest.approx(-10.0)
    assert (lv.prev_low, lv.prev_high) == (109.0, 111.0)
    assert (lv.low_20d, lv.high_20d) == (98.0, 111.0)
    assert lv.sma_50 is None and lv.sma_200 is None  # not enough history


def test_moving_averages_with_enough_history():
    lv = compute_levels("SPY", bars([float(i) for i in range(1, 251)]))
    assert lv.sma_50 == pytest.approx(sum(range(201, 251)) / 50)
    assert lv.sma_200 == pytest.approx(sum(range(51, 251)) / 200)


def test_twenty_day_window_ignores_older_bars():
    lv = compute_levels("QQQ", bars([500.0] + [100.0] * 20))
    assert lv.high_20d == 101.0


def test_needs_two_bars():
    with pytest.raises(MarketDataError):
        compute_levels("QQQ", bars([100.0]))


class FakeIB:
    def __init__(self, bars_by_symbol=None, connect_error=None):
        self.bars_by_symbol = bars_by_symbol or {}
        self.connect_error = connect_error
        self.connected = False
        self.connect_kwargs = None

    def connect(self, host, port, **kwargs):
        if self.connect_error:
            raise self.connect_error
        self.connect_kwargs = {"host": host, "port": port, **kwargs}
        self.connected = True

    def qualifyContracts(self, contract):
        return [contract]

    def reqHistoricalData(self, contract, **kwargs):
        closes = self.bars_by_symbol.get(contract.symbol, [])
        return [SimpleNamespace(high=c + 1, low=c - 1, close=c) for c in closes]

    def isConnected(self):
        return self.connected

    def disconnect(self):
        self.connected = False


def test_fetch_levels_connects_read_only_and_disconnects():
    ib = FakeIB({"QQQ": [100.0, 101.0], "SPY": [400.0, 404.0]})
    levels = IbkrMarketData(SETTINGS, ib_factory=lambda: ib).fetch_levels(("QQQ", "SPY"))
    assert levels["QQQ"].last == 101.0 and levels["SPY"].last == 404.0
    assert ib.connect_kwargs["readonly"] is True
    assert ib.connect_kwargs["clientId"] == 77
    assert not ib.connected


def test_connection_failure_has_helpful_message():
    ib = FakeIB(connect_error=ConnectionRefusedError())
    with pytest.raises(MarketDataError, match="Is it running"):
        IbkrMarketData(SETTINGS, ib_factory=lambda: ib).fetch_levels(("QQQ",))


def test_no_data_has_helpful_message_and_still_disconnects():
    ib = FakeIB({})
    with pytest.raises(MarketDataError, match="market data"):
        IbkrMarketData(SETTINGS, ib_factory=lambda: ib).fetch_levels(("QQQ",))
    assert not ib.connected
