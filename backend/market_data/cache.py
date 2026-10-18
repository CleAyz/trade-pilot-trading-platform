from datetime import date, timedelta
from pathlib import Path
import os
import sqlite3

from backend.market_data.models import DailyBar


class DailyBarCache:
    """Small local SQLite cache so repeated scans do not re-download full history."""

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or os.getenv("TRADEPILOT_CACHE_PATH", "work/market_data.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                create table if not exists daily_bars (
                    symbol text not null,
                    trading_date text not null,
                    open real not null,
                    high real not null,
                    low real not null,
                    close real not null,
                    volume integer not null,
                    adjusted integer not null,
                    source text not null,
                    primary key (symbol, trading_date)
                )
                """
            )

    def latest_date(self, symbol: str) -> date | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "select max(trading_date) from daily_bars where symbol = ?",
                (symbol,),
            ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def save(self, bars: list[DailyBar]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.executemany(
                """
                insert into daily_bars
                    (symbol, trading_date, open, high, low, close, volume, adjusted, source)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(symbol, trading_date) do update set
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume,
                    adjusted=excluded.adjusted, source=excluded.source
                """,
                [
                    (
                        bar.symbol, bar.trading_date.isoformat(), float(bar.open), float(bar.high),
                        float(bar.low), float(bar.close), bar.volume, int(bar.adjusted), bar.source,
                    )
                    for bar in bars
                ],
            )

    def load(self, symbols: list[str], start: date, end: date) -> list[DailyBar]:
        placeholders = ",".join("?" for _ in symbols)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                f"""
                select symbol, trading_date, open, high, low, close, volume, adjusted, source
                from daily_bars
                where symbol in ({placeholders}) and trading_date between ? and ?
                order by symbol, trading_date
                """,
                [*symbols, start.isoformat(), end.isoformat()],
            ).fetchall()
        return [
            DailyBar(
                symbol=row[0], trading_date=date.fromisoformat(row[1]), open=row[2], high=row[3],
                low=row[4], close=row[5], volume=row[6], adjusted=bool(row[7]), source=row[8],
            )
            for row in rows
        ]


class CachedYahooMarketDataProvider:
    name = "yahoo_yfinance_personal_cached"

    def __init__(self, provider, cache: DailyBarCache | None = None) -> None:
        self.provider = provider
        self.cache = cache or DailyBarCache()

    def daily_bars(self, symbols: list[str], start: date, end: date) -> list[DailyBar]:
        normalized = sorted({symbol.upper() for symbol in symbols})
        if not normalized:
            return []
        fetch_start = start
        for symbol in normalized:
            latest = self.cache.latest_date(symbol)
            if latest:
                fetch_start = min(fetch_start, max(start, latest - timedelta(days=5)))
        fresh = self.provider.daily_bars(normalized, fetch_start, end)
        self.cache.save(fresh)
        return self.cache.load(normalized, start, end)
