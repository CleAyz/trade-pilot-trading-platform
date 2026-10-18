from datetime import date

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
