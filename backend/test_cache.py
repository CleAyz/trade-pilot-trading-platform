from datetime import date
from datetime import timedelta

from backend.market_data.cache import CachedYahooMarketDataProvider, DailyBarCache
from backend.market_data.models import DailyBar


class FakeProvider:
    def __init__(self):
        self.calls = []

    def daily_bars(self, symbols, start, end):
        self.calls.append((symbols, start, end))
        return [DailyBar(symbol=symbols[0], trading_date=start, open=1, high=2, low=1, close=2, volume=100, adjusted=False, source="fake")]


def test_cache_reuses_saved_bars(tmp_path):
    fake = FakeProvider()
    provider = CachedYahooMarketDataProvider(fake, DailyBarCache(str(tmp_path / "bars.sqlite3")))
    start = date(2025, 1, 1)
    end = date(2025, 1, 2)

    first = provider.daily_bars(["AAPL"], start, end)
    second = provider.daily_bars(["AAPL"], start, end)

    assert len(first) == 1
    assert len(second) == 1
    assert len(fake.calls) == 2  # refreshes a small recent window, not the full history


def test_cached_ticker_does_not_force_new_ticker_to_redownload_history(tmp_path):
    cache = DailyBarCache(str(tmp_path / "bars.sqlite3"))
    latest = date(2026, 11, 16)
    cache.save([DailyBar(symbol="AAPL", trading_date=latest, open=1, high=2, low=1, close=2, volume=100, adjusted=False, source="fake")])
    fake = FakeProvider()
    provider = CachedYahooMarketDataProvider(fake, cache)
    provider.daily_bars(["AAPL", "MSFT"], date(2025, 1, 1), latest + timedelta(days=2))
    starts = {symbols[0]: start for symbols, start, _ in fake.calls}
    assert starts["AAPL"] == latest - timedelta(days=5)
    assert starts["MSFT"] == date(2025, 1, 1)
