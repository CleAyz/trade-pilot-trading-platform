from datetime import date
from os import getenv

import httpx

from backend.market_data.models import DailyBar, MarketDataNotConfigured, MarketDataProviderError


class AlpacaMarketDataProvider:
    """Alpaca historical equities provider using the free IEX feed."""

    name = "alpaca_iex"

    def __init__(self, api_key: str | None = None, secret_key: str | None = None) -> None:
        self.api_key = api_key or getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or getenv("ALPACA_SECRET_KEY")
        self.base_url = getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")

    def daily_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> list[DailyBar]:
        if not self.api_key or not self.secret_key:
            raise MarketDataNotConfigured("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
        if not symbols:
            return []
        if start > end:
            raise ValueError("start must be on or before end")

        response = httpx.get(
            f"{self.base_url.rstrip('/')}/v2/stocks/bars",
            headers={
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
            },
            params={
                "symbols": ",".join(sorted({symbol.upper() for symbol in symbols})),
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "adjustment": "all",
                "feed": "iex",
                "limit": 10000,
            },
            timeout=30.0,
        )
        if not response.is_success:
            raise MarketDataProviderError(f"Alpaca returned HTTP {response.status_code}")

        try:
            payload = response.json()
            return [
                DailyBar(
                    symbol=symbol,
                    trading_date=bar["t"][:10],
                    open=bar["o"],
                    high=bar["h"],
                    low=bar["l"],
                    close=bar["c"],
                    volume=bar["v"],
                    adjusted=True,
                    source=self.name,
                )
                for symbol, bars in payload.get("bars", {}).items()
                for bar in bars
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketDataProviderError("Alpaca returned an invalid bars payload") from exc
