from datetime import date, timedelta
from os import getenv

import pandas as pd

from backend.market_data.cache import CachedYahooMarketDataProvider
from backend.market_data.yahoo import YahooMarketDataProvider

DEFAULT_UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "LLY", "JPM", "ORCL"]


def run_basic_scan(symbols: list[str] | None = None, report: list[dict] | None = None) -> list[dict]:
    universe = symbols or [s.strip().upper() for s in getenv("TRADEPILOT_SCANNER_SYMBOLS", ",".join(DEFAULT_UNIVERSE)).split(",") if s.strip()]
    end = date.today()
    start = end - timedelta(days=420)
    bars = CachedYahooMarketDataProvider(YahooMarketDataProvider()).daily_bars(universe, start, end)
    by_symbol: dict[str, list] = {}
    for bar in bars:
        by_symbol.setdefault(bar.symbol, []).append(bar)
    results: list[dict] = []

    for symbol in universe:
        rows = by_symbol.get(symbol, [])
        if len(rows) < 200:
            if report is not None:
                report.append({"ticker": symbol, "status": "missing_data", "reason": f"Only {len(rows)} daily bars (need 200)"})
            continue
        frame = pd.DataFrame([row.model_dump() for row in rows]).sort_values("trading_date")
        close = frame["close"].astype(float)
        volume = frame["volume"].astype(float)
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        avg_volume20 = volume.rolling(20).mean().iloc[-1]
        previous_close = close.shift(1)
        true_range = pd.concat(
            [
                frame["high"].astype(float) - frame["low"].astype(float),
                (frame["high"].astype(float) - previous_close).abs(),
                (frame["low"].astype(float) - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr14 = true_range.rolling(14).mean().iloc[-1]
        current = close.iloc[-1]
        dollar_volume = (close * volume).rolling(20).mean().iloc[-1]
        movement = float(atr14) / float(current) if current else 0
        liquid = current >= 5 and dollar_volume >= 20_000_000 and movement >= 0.015
        relative_volume = volume.iloc[-1] / avg_volume20 if avg_volume20 else 0
        recent_high = close.iloc[-21:-1].max()
        trend = current > sma50 and current > sma200
        breakout = current >= recent_high * 0.98
        volume_confirmed = relative_volume >= 1.2
        score = round(45 + (20 if trend else 0) + (20 if breakout else 0) + min(relative_volume * 10, 15), 1)
        if trend and breakout and liquid:
            if report is not None:
                report.append({"ticker": symbol, "status": "qualified", "reason": "Uptrend and near 20-day high"})
            support = float(recent_high) - float(atr14) * 1.5
            stop_loss = min(current - float(atr14), support)
            risk_per_share = max(current - stop_loss, float(atr14) * 0.5)
            target_price = current + risk_per_share * 2
            results.append({
                "ticker": symbol,
                "setup": "Momentum Breakout",
                "score": float(min(score, 100)),
                "price": round(current, 2),
                "entry_price": round(current, 2),
                "stop_loss": round(stop_loss, 2),
                "target_price": round(target_price, 2),
                "risk_reward": 2.0,
                "explanation": "Above the 50/200-day averages and near a 20-day high, with at least $20M average daily value and 1.5% ATR.",
                "atr14": round(float(atr14), 2),
                "sma50": round(sma50, 2),
                "sma200": round(sma200, 2),
                "relative_volume": round(relative_volume, 2),
                "volume_confirmed": bool(volume_confirmed),
                "signal_date": str(frame["trading_date"].iloc[-1]),
                "source": "Yahoo Finance via yfinance; personal development mode",
            })
        elif report is not None:
            reasons = []
            if not trend:
                reasons.append("Below 50-day or 200-day average")
            if not breakout:
                reasons.append("Not near 20-day high")
            if current < 5:
                reasons.append("Price under $5")
            if dollar_volume < 20_000_000:
                reasons.append("Average daily trading value under $20M")
            if movement < 0.015:
                reasons.append("ATR under 1.5% of price")
            report.append({"ticker": symbol, "status": "rejected", "reason": "; ".join(reasons)})
    return sorted(results, key=lambda item: item["score"], reverse=True)
