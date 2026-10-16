from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class DailyBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adjusted: bool
    source: str


class MarketDataNotConfigured(Exception):
    """Raised when the selected provider has no credentials configured."""


class MarketDataProviderError(Exception):
    """Raised when a provider request fails or returns invalid data."""
