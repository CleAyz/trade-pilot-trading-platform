from datetime import date

import pytest

from backend.market_data.alpaca import AlpacaMarketDataProvider
from backend.market_data.models import MarketDataNotConfigured


def test_alpaca_requires_credentials():
    provider = AlpacaMarketDataProvider(api_key=None, secret_key=None)

    with pytest.raises(MarketDataNotConfigured):
        provider.daily_bars(["AAPL"], date(2025, 1, 1), date(2025, 1, 2))


def test_alpaca_rejects_reversed_date_range():
    provider = AlpacaMarketDataProvider(api_key="test", secret_key="test")

    with pytest.raises(ValueError, match="start"):
        provider.daily_bars(["AAPL"], date(2025, 1, 2), date(2025, 1, 1))
