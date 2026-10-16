from os import getenv

from backend.market_data.alpaca import AlpacaMarketDataProvider


def get_market_data_provider() -> AlpacaMarketDataProvider:
    provider = getenv("TRADEPILOT_MARKET_DATA_PROVIDER", "alpaca_iex")
    if provider != "alpaca_iex":
        raise ValueError(f"Unsupported market-data provider: {provider}")
    return AlpacaMarketDataProvider()
