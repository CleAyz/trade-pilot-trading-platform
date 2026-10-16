from datetime import date

import yfinance as yf
from pandas import MultiIndex

from backend.market_data.models import DailyBar, MarketDataProviderError


class YahooMarketDataProvider:
    """No-key development provider backed by yfinance/Yahoo Finance."""

    name = "yahoo_yfinance_personal"

    def daily_bars(self, symbols: list[str], start: date, end: date) -> list[DailyBar]:
        if not symbols:
            return []
        if start > end:
            raise ValueError("start must be on or before end")

        try:
            frame = yf.download(
                tickers=sorted({symbol.upper() for symbol in symbols}),
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=False,
                actions=False,
                progress=False,
                group_by="ticker",
                threads=False,
            )
        except Exception as exc:
            raise MarketDataProviderError("Yahoo Finance request failed") from exc

        bars: list[DailyBar] = []
        for symbol in sorted({symbol.upper() for symbol in symbols}):
            try:
                series = frame[symbol] if isinstance(frame.columns, MultiIndex) else frame
                for timestamp, row in series.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).iterrows():
                    bars.append(
                        DailyBar(
                            symbol=symbol,
                            trading_date=timestamp.date(),
                            open=row["Open"],
                            high=row["High"],
                            low=row["Low"],
                            close=row["Close"],
                            volume=int(row["Volume"]),
                            adjusted=False,
                            source=self.name,
                        )
                    )
            except (KeyError, TypeError, ValueError) as exc:
                raise MarketDataProviderError(f"Yahoo returned invalid data for {symbol}") from exc
        return bars
