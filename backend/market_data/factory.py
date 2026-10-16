from os import getenv

from backend.market_data.alpaca import AlpacaMarketDataProvider
from backend.market_data.yahoo import YahooMarketDataProvider


def get_market_data_provider() -> AlpacaMarketDataProvider | YahooMarketDataProvider:
    provider = getenv("TRADEPILOT_MARKET_DATA_PROVIDER", "yahoo_yfinance_personal")
    if provider == "alpaca_iex":
        return AlpacaMarketDataProvider()
    if provider == "yahoo_yfinance_personal":
        return YahooMarketDataProvider()
    raise ValueError(f"Unsupported market-data provider: {provider}")
