from datetime import date, timedelta
from os import getenv

import pandas as pd

from backend.market_data.cache import CachedYahooMarketDataProvider
from backend.market_data.yahoo import YahooMarketDataProvider

DEFAULT_UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "LLY", "JPM", "ORCL"]


def run_basic_scan(symbols: list[str] | None = None) -> list[dict]:
    universe = symbols or [s.strip().upper() for s in getenv("TRADEPILOT_SCANNER_SYMBOLS", ",".join(DEFAULT_UNIVERSE)).split(",") if s.strip()]
    end = date.today()
    start = end - timedelta(days=420)
    bars = CachedYahooMarketDataProvider(YahooMarketDataProvider()).daily_bars(universe, start, end)
    results: list[dict] = []

    for symbol in universe:
        rows = [bar for bar in bars if bar.symbol == symbol]
        if len(rows) < 200:
            continue
        frame = pd.DataFrame([row.model_dump() for row in rows]).sort_values("trading_date")
        close = frame["close"].astype(float)
        volume = frame["volume"].astype(float)
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        avg_volume20 = volume.rolling(20).mean().iloc[-1]
        current = close.iloc[-1]
        relative_volume = volume.iloc[-1] / avg_volume20 if avg_volume20 else 0
        recent_high = close.iloc[-21:-1].max()
        trend = current > sma50 and current > sma200
        breakout = current >= recent_high * 0.98
        volume_confirmed = relative_volume >= 1.2
        score = round(45 + (20 if trend else 0) + (20 if breakout else 0) + min(relative_volume * 10, 15), 1)
        if trend and breakout:
            results.append({
                "ticker": symbol,
                "setup": "Momentum Breakout",
                "score": float(min(score, 100)),
                "price": round(current, 2),
                "sma50": round(sma50, 2),
                "sma200": round(sma200, 2),
                "relative_volume": round(relative_volume, 2),
                "volume_confirmed": bool(volume_confirmed),
                "signal_date": str(frame["trading_date"].iloc[-1]),
                "source": "Yahoo Finance via yfinance; personal development mode",
            })
    return sorted(results, key=lambda item: item["score"], reverse=True)
