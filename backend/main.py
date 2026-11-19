import asyncio
import logging
import time
from threading import Lock, Thread
from uuid import uuid4
from contextlib import asynccontextmanager, suppress
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
from backend.portfolio import PortfolioStoreError, get_portfolio_summary, save_account, sync_ibkr_portfolio
from backend.ibkr import IBKRConnectionError, read_ibkr_portfolio
from backend.alerts import AlertService
from backend.signals_store import (
    SignalStoreError,
    add_watchlist,
    delete_watchlist,
    list_history,
    list_watchlist,
    mark_reviewed,
    save_scan,
    update_watchlist,
)
from backend.universe import get_universe

load_dotenv("backend/.env")

logger = logging.getLogger("tradepilot.ibkr")
ibkr_sync_state = {"state": "not_started", "last_sync": None, "last_error": None}
alert_service = AlertService()
alert_state = {
    "state": "not_started",
    "last_run": None,
    "last_error": None,
    "last_result": None,
}
scan_jobs: dict[str, dict] = {}
scan_lock = Lock()


def _ibkr_sync_enabled() -> bool:
    return getenv("IBKR_SYNC_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def _alerts_enabled() -> bool:
    return getenv("TRADEPILOT_ALERTS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _run_alert_scan(symbols: list[str] | None = None) -> tuple[list[dict], dict, datetime]:
    scanned_at = datetime.now(UTC)
    signals = run_basic_scan(symbols)
    result = alert_service.process(signals)
    return signals, result, scanned_at


async def _ibkr_sync_loop() -> None:
    interval = max(int(getenv("IBKR_SYNC_INTERVAL_SECONDS", "300")), 60)
    while True:
        try:
            snapshot = await asyncio.to_thread(read_ibkr_portfolio)
            await asyncio.to_thread(sync_ibkr_portfolio, snapshot)
            ibkr_sync_state.update(state="connected", last_sync=datetime.now(UTC), last_error=None)
            logger.info("IBKR portfolio synced to Supabase")
        except (IBKRConnectionError, PortfolioStoreError, ValueError) as exc:
            ibkr_sync_state.update(state="offline", last_error=str(exc))
            logger.warning("IBKR sync unavailable: %s", exc)
        await asyncio.sleep(interval)


async def _alert_loop() -> None:
    interval = max(int(getenv("TRADEPILOT_ALERT_INTERVAL_SECONDS", "900")), 300)
    while True:
        try:
            _, result, scanned_at = await asyncio.to_thread(_run_alert_scan)
            alert_state.update(state="ready" if not result["errors"] else "degraded", last_run=scanned_at, last_error=None, last_result=result)
            logger.info("Alert scan complete: %s", result)
        except Exception as exc:  # keep the background service alive after provider failures
            alert_state.update(state="error", last_run=datetime.now(UTC), last_error=str(exc))
            logger.warning("Alert scan unavailable: %s", exc)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_ibkr_sync_loop()) if _ibkr_sync_enabled() else None
    alert_task = asyncio.create_task(_alert_loop()) if _alerts_enabled() else None
    if task is None:
        ibkr_sync_state["state"] = "disabled"
    if alert_task is None:
        alert_state["state"] = "disabled"
    try:
        yield
    finally:
        for background_task in (task, alert_task):
            if background_task:
                background_task.cancel()
                with suppress(asyncio.CancelledError):
                    await background_task


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
    universe: str | None = None


class ScannerResponse(BaseModel):
    source: str
    count: int
    scanned_count: int
    scanned_at: datetime
    signals: list[dict]
    history_saved: bool = False
    unread_count: int = 0
    outcomes: list[dict] = []
    failed_count: int = 0


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


class IBKRSyncStatusResponse(BaseModel):
    state: str
    last_sync: datetime | None
    last_error: str | None


class AlertStatusResponse(BaseModel):
    state: str
    enabled: bool
    notifier_configured: bool
    interval_seconds: int
    last_run: datetime | None
    last_error: str | None
    last_result: dict | None


class AlertRunRequest(BaseModel):
    symbols: list[str] | None = None


class AlertRunResponse(BaseModel):
    source: str
    count: int
    scanned_count: int
    scanned_at: datetime
    new_signals: int
    alerts_sent: int
    pending: int
    errors: list[str]


class ReviewRequest(BaseModel):
    reviewed: bool = True


class WatchlistRequest(BaseModel):
    ticker: str
    notes: str = ""
    status: str = "watching"
    signal_id: str | None = None


class WatchlistUpdateRequest(BaseModel):
    notes: str | None = None
    status: str | None = None


app = FastAPI(
    title="TradePilot API",
    version="0.1.0",
    description="Private server-side API foundation for the TradePilot trading workspace.",
    lifespan=lifespan,
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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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
    if request.universe:
        try:
            symbols = get_universe(request.universe)
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        symbols = request.symbols or DEFAULT_UNIVERSE
    symbols = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
    outcomes: list[dict] = []
    try:
        signals = run_basic_scan(symbols, report=outcomes)
    except MarketDataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    scanned_at = datetime.now(UTC)
    try:
        saved = save_scan(signals, scanned_at)
        unread = len(list_history(unread_only=True, limit=200))
    except SignalStoreError as exc:
        logger.warning("Signal history unavailable: %s", exc)
        saved, unread = [], 0
    return ScannerResponse(
        source="yahoo_yfinance_personal",
        count=len(signals),
        scanned_count=len(symbols),
        scanned_at=scanned_at,
        signals=signals,
        history_saved=bool(saved) or not signals,
        unread_count=unread,
        outcomes=outcomes,
    )


def _scan_job(job_id: str, symbols: list[str]) -> None:
    job = scan_jobs[job_id]
    signals: list[dict] = []
    outcomes: list[dict] = []
    for index in range(0, len(symbols), 25):
        batch = symbols[index:index + 25]
        for attempt in range(2):
            try:
                signals.extend(run_basic_scan(batch, report=outcomes))
                break
            except (MarketDataProviderError, ValueError) as exc:
                if attempt == 0:
                    time.sleep(2)
                else:
                    outcomes.extend({"ticker": s, "status": "failed", "reason": str(exc)} for s in batch)
        with scan_lock:
            job.update(processed=min(index + 25, len(symbols)), qualified=len(signals), failed=sum(o["status"] in {"failed", "missing_data"} for o in outcomes))
    try:
        scanned_at = datetime.now(UTC)
        saved = save_scan(signals, scanned_at)
        history_saved = bool(saved) or not signals
    except SignalStoreError as exc:
        history_saved = False
        logger.warning("Signal history unavailable: %s", exc)
    with scan_lock:
        job.update(state="completed", signals=sorted(signals, key=lambda s: s["score"], reverse=True), outcomes=outcomes, history_saved=history_saved, scanned_at=scanned_at.isoformat())


@app.get("/api/scanner/universes", tags=["scanner"])
def scanner_universes() -> dict:
    return {"presets": ["sp500", "nasdaq100", "combined"], "source": "community-maintained index lists"}


@app.post("/api/scanner/jobs", tags=["scanner"])
def start_scan_job(request: ScannerRequest) -> dict:
    try:
        symbols = get_universe(request.universe) if request.universe else request.symbols or DEFAULT_UNIVERSE
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    symbols = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
    if not symbols or len(symbols) > 700:
        raise HTTPException(status_code=422, detail="Choose between 1 and 700 symbols")
    with scan_lock:
        if any(job["state"] == "running" for job in scan_jobs.values()):
            raise HTTPException(status_code=409, detail="A scan is already running")
        job_id = str(uuid4())
        scan_jobs[job_id] = {"id": job_id, "state": "running", "total": len(symbols), "processed": 0, "qualified": 0, "failed": 0}
    Thread(target=_scan_job, args=(job_id, symbols), daemon=True).start()
    return scan_jobs[job_id]


@app.get("/api/scanner/jobs/{job_id}", tags=["scanner"])
def get_scan_job(job_id: str) -> dict:
    with scan_lock:
        if job_id not in scan_jobs:
            raise HTTPException(status_code=404, detail="Scan not found (the API may have restarted)")
        return dict(scan_jobs[job_id])


@app.post("/api/signals/scan", response_model=ScannerResponse, tags=["signals"])
def signals_scan(request: ScannerRequest) -> ScannerResponse:
    return scanner_run(request)


@app.get("/api/signals/history", response_model=list[dict], tags=["signals"])
def signals_history(unread_only: bool = False, limit: int = 100) -> list[dict]:
    try:
        return list_history(unread_only, limit)
    except SignalStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/signals/{signal_id}/review", response_model=dict, tags=["signals"])
def signal_review(signal_id: str, request: ReviewRequest) -> dict:
    if not request.reviewed:
        raise HTTPException(status_code=400, detail="Signals can only be marked reviewed")
    try:
        return mark_reviewed(signal_id)
    except SignalStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/watchlist", response_model=list[dict], tags=["watchlist"])
def watchlist() -> list[dict]:
    try:
        return list_watchlist()
    except SignalStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/watchlist", response_model=dict, tags=["watchlist"])
def watchlist_add(request: WatchlistRequest) -> dict:
    if request.status not in {"watching", "triggered", "invalidated", "archived"}:
        raise HTTPException(status_code=422, detail="Invalid watchlist status")
    try:
        return add_watchlist(request.ticker, request.notes, request.status, request.signal_id)
    except SignalStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.patch("/api/watchlist/{item_id}", response_model=dict, tags=["watchlist"])
def watchlist_update(item_id: str, request: WatchlistUpdateRequest) -> dict:
    payload = request.model_dump(exclude_none=True)
    if "status" in payload and payload["status"] not in {"watching", "triggered", "invalidated", "archived"}:
        raise HTTPException(status_code=422, detail="Invalid watchlist status")
    try:
        return update_watchlist(item_id, payload)
    except SignalStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.delete("/api/watchlist/{item_id}", status_code=204, tags=["watchlist"])
def watchlist_delete(item_id: str) -> None:
    try:
        delete_watchlist(item_id)
    except SignalStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/alerts/run", response_model=AlertRunResponse, tags=["alerts"])
def alerts_run(request: AlertRunRequest) -> AlertRunResponse:
    """Scan and deliver only new signals; duplicate signals are persisted and skipped."""
    try:
        signals, result, scanned_at = _run_alert_scan(request.symbols)
    except MarketDataProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    alert_state.update(
        state="ready" if not result["errors"] else "degraded",
        last_run=scanned_at,
        last_error=None,
        last_result=result,
    )
    return AlertRunResponse(
        source="yahoo_yfinance_personal",
        count=len(signals),
        scanned_count=len(request.symbols or DEFAULT_UNIVERSE),
        scanned_at=scanned_at,
        **result,
    )


@app.get("/api/alerts/status", response_model=AlertStatusResponse, tags=["alerts"])
def alerts_status() -> AlertStatusResponse:
    """Report scheduler and Telegram readiness without exposing the bot token."""
    return AlertStatusResponse(
        state=alert_state["state"],
        enabled=_alerts_enabled(),
        notifier_configured=alert_service.notifier.configured,
        interval_seconds=max(int(getenv("TRADEPILOT_ALERT_INTERVAL_SECONDS", "900")), 300),
        last_run=alert_state["last_run"],
        last_error=alert_state["last_error"],
        last_result=alert_state["last_result"],
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
    """Read and persist balances and positions from a local IBKR TWS/Gateway session."""
    try:
        snapshot = read_ibkr_portfolio()
        sync_ibkr_portfolio(snapshot)
        ibkr_sync_state.update(state="connected", last_sync=datetime.now(UTC), last_error=None)
        return IBKRPortfolioResponse(**snapshot)
    except (IBKRConnectionError, PortfolioStoreError) as exc:
        ibkr_sync_state.update(state="offline", last_error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/ibkr/status", response_model=IBKRSyncStatusResponse, tags=["ibkr"])
def ibkr_status() -> IBKRSyncStatusResponse:
    """Report the background sync state without exposing account data or credentials."""
    return IBKRSyncStatusResponse(**ibkr_sync_state)
