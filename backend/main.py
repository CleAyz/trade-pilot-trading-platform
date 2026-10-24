from datetime import UTC, datetime
from os import getenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from backend.supabase_connection import check_supabase_connection
from backend.scanner import DEFAULT_UNIVERSE, run_basic_scan
from backend.market_data.models import MarketDataProviderError
from backend.market_data.cache import DailyBarCache
from backend.portfolio import PortfolioStoreError, get_portfolio_summary, save_account
from backend.ibkr import IBKRConnectionError, read_ibkr_portfolio

load_dotenv("backend/.env")


class HealthResponse(BaseModel):
    status: str
    service: str
    demo_mode: bool
    data_provider: str
    checked_at: datetime


class SupabaseStatusResponse(BaseModel):
    configured: bool
    state: str


class ScannerRequest(BaseModel):
    symbols: list[str] | None = None


class ScannerResponse(BaseModel):
    source: str
    count: int
    scanned_count: int
    scanned_at: datetime
    signals: list[dict]


class MarketDataResponse(BaseModel):
    source: str
    count: int
    rows: list[dict]


class AccountSettings(BaseModel):
    base_currency: str = "SGD"
    account_value: float
    available_cash: float
    risk_per_trade: float = 0.5
    max_position_allocation: float = 20
    max_positions: int = 4


class PortfolioResponse(BaseModel):
    account: dict | None
    positions: list[dict]
    account_value: float
    available_cash: float
    allocated_cash: float
    open_positions: int
    planned_risk: float


class IBKRPortfolioResponse(BaseModel):
    account_id: str
    base_currency: str
    account_value: float
    available_cash: float
    positions: list[dict]
    source: str


app = FastAPI(
    title="TradePilot API",
    version="0.1.0",
    description="Private server-side API foundation for the TradePilot trading workspace.",
)

# Keep this narrow for local development. Production origins should be set explicitly
# when the frontend and API are deployed behind access controls.
frontend_origins = [
    origin.strip()
    for origin in getenv(
        "TRADEPILOT_FRONTEND_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Report API availability without exposing credentials or provider secrets."""
    provider = getenv("TRADEPILOT_MARKET_DATA_PROVIDER", "not_configured")
    return HealthResponse(
        status="ok",
        service="tradepilot-api",
        demo_mode=provider == "not_configured",
        data_provider=provider,
        checked_at=datetime.now(UTC),
    )


@app.get("/api/supabase/status", response_model=SupabaseStatusResponse, tags=["system"])
def supabase_status() -> SupabaseStatusResponse:
    """Check Supabase reachability without returning credentials or response payloads."""
    reachable, state = check_supabase_connection()
    return SupabaseStatusResponse(configured=reachable, state=state)


@app.post("/api/scanner/run", response_model=ScannerResponse, tags=["scanner"])
def scanner_run(request: ScannerRequest) -> ScannerResponse:
    try:
        signals = run_basic_scan(request.symbols)
    except MarketDataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ScannerResponse(
        source="yahoo_yfinance_personal",
        count=len(signals),
        scanned_count=len(request.symbols or DEFAULT_UNIVERSE),
        scanned_at=datetime.now(UTC),
        signals=signals,
    )


@app.get("/api/market-data", response_model=MarketDataResponse, tags=["market-data"])
def market_data(symbol: str | None = None, limit: int = 100) -> MarketDataResponse:
    """Read cached daily bars for inspection without exposing filesystem paths."""
    safe_limit = min(max(limit, 1), 500)
    rows = DailyBarCache().recent(symbol=symbol, limit=safe_limit)
    return MarketDataResponse(
        source="local_sqlite_cache",
        count=len(rows),
        rows=[row.model_dump(mode="json") for row in rows],
    )


@app.get("/api/portfolio/summary", response_model=PortfolioResponse, tags=["portfolio"])
def portfolio_summary() -> PortfolioResponse:
    try:
        return PortfolioResponse(**get_portfolio_summary())
    except PortfolioStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/portfolio/account", response_model=dict, tags=["portfolio"])
def portfolio_account(settings: AccountSettings) -> dict:
    if settings.account_value < 0 or settings.available_cash < 0:
        raise HTTPException(status_code=422, detail="Account value and available cash cannot be negative")
    if settings.available_cash > settings.account_value:
        raise HTTPException(status_code=422, detail="Available cash cannot exceed account value")
    try:
        return save_account(settings.model_dump())
    except PortfolioStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/ibkr/portfolio", response_model=IBKRPortfolioResponse, tags=["ibkr"])
def ibkr_portfolio() -> IBKRPortfolioResponse:
    """Read balances and positions from a locally running IBKR TWS/Gateway session."""
    try:
        return IBKRPortfolioResponse(**read_ibkr_portfolio())
    except IBKRConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
