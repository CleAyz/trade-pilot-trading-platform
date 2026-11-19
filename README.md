# TradePilot

TradePilot is a single-user swing-trading signal workspace. It scans a custom ticker universe, saves signal history and a manual watchlist in Supabase, and never places orders.

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

When deploying the dashboard, set `NEXT_PUBLIC_API_BASE_URL` to the public FastAPI service URL (for example, your Render `onrender.com` URL). If unset, local development uses `http://localhost:8000`.

## FastAPI backend

The initial backend is in `backend/`. It exposes `GET /api/health` and intentionally reports Demo Mode until `TRADEPILOT_MARKET_DATA_PROVIDER` is configured.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

The API docs are available at `http://localhost:8000/docs`. Run the backend test with `pytest` from the repository root.

## Market-data provider

The default development provider is Yahoo Finance through `yfinance`, so the scanner can run without API keys. This is intended for private personal development and should not be treated as a guaranteed production feed. Alpaca's free IEX provider is also implemented as an optional provider; set `TRADEPILOT_MARKET_DATA_PROVIDER=alpaca_iex` and add Alpaca credentials to use it. The provider abstraction keeps both options replaceable without changing scanner code.

## Run a scanner

Run the dashboard and choose **S&P 500**, **Nasdaq 100**, **S&P 500 + Nasdaq 100**, or your own comma-separated list on **Daily Scanner**. The app scans 25 stocks at a time and shows progress and a reason for each result. Index lists are refreshed daily from [community S&P data](https://github.com/datasets/s-and-p-500-companies) and [community Nasdaq 100 data](https://github.com/Gary-Strauss/NASDAQ100_Constituents), then cached locally. These are not official index membership feeds. The API also exposes `POST /api/scanner/jobs`, `GET /api/scanner/jobs/{id}`, `POST /api/signals/scan`, and `GET /api/signals/history`. Signals are research output, not trading recommendations.

Qualifying signals require price at least $5, 20-day average daily trading value at least $20 million, ATR at least 1.5% of price, an uptrend above both the 50/200-day averages, and a price near the recent 20-day high. The initial scan of hundreds of symbols can take several minutes; later scans reuse local daily-bar history.

For the dashboard to call the scanner, run both services in separate terminals:

```bash
# Terminal 1
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# Terminal 2
npm run dev
```

Then open `http://localhost:3000` and click **Run scanner**. The button calls the real FastAPI endpoint and replaces the illustrative opportunity table with the returned signals.

## Signal history and watchlist

Apply `supabase/migrations/0003_signal_history_watchlist.sql` in the Supabase SQL Editor after the earlier migrations. Scans then persist in `signal_history`, survive refreshes/restarts, and can be marked reviewed. The **Stock Analysis** page can add a ticker to **Watchlist**, where notes and statuses (`watching`, `triggered`, `invalidated`, `archived`) are editable.

Daily bars are cached in `work/market_data.sqlite3`, which is ignored by Git. The first scan downloads the historical window; later scans refresh only a small recent window and read the rest locally. Delete the cache file only if you intentionally want to rebuild the local history.

## Signal alerts

TradePilot can run the scanner in the FastAPI background process and send only new signals to Telegram. Alerts are research notifications; TradePilot never places an IBKR order.

Create a Telegram bot with BotFather, obtain the bot token and your chat ID, then add them to `backend/.env`:

```env
TRADEPILOT_ALERTS_ENABLED=true
TRADEPILOT_ALERT_INTERVAL_SECONDS=900
TRADEPILOT_TELEGRAM_BOT_TOKEN=your-token
TRADEPILOT_TELEGRAM_CHAT_ID=your-chat-id
```

The scheduler runs at the configured interval, with a five-minute minimum. It stores signal fingerprints in the local SQLite cache, so the same ticker/setup/day is not repeatedly sent. Use `GET /api/alerts/status` to check readiness and `POST /api/alerts/run` to run an alert scan immediately. Without Telegram credentials, signals are stored as pending and the status endpoint reports the configuration problem.

The current scanner uses daily Yahoo Finance data, so this is designed for swing-trading alerts rather than second-by-second or intraday execution alerts.

## Portfolio and execution

Portfolio and IBKR account syncing are intentionally outside the current dashboard workflow. Execute trades manually in IBKR after reviewing a signal. The existing backend IBKR endpoints remain available for later reuse, but the UI does not depend on them.

## Optional IBKR Gateway connection

TradePilot can read account value, available funds, and open positions through IBKR Gateway/TWS using the local socket API. It does not place orders. Configure `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, and `IBKR_BASE_CURRENCY` in `backend/.env`, start IB Gateway with API socket access enabled, and keep it running. Set `IBKR_SYNC_ENABLED=true` and optionally adjust `IBKR_SYNC_INTERVAL_SECONDS` (default: 300). FastAPI will sync successful snapshots into Supabase in the background; the Portfolio page can also use **Sync from IBKR** for an immediate refresh.

## Planned architecture

```text
app/                 Next.js routes and dashboard UI
components/          Reusable terminal UI primitives
lib/                 Typed client helpers and formatting
backend/             FastAPI application
  alerts.py          Signal deduplication and Telegram delivery
  market_data/       Provider-neutral interfaces and adapters
  indicators/        Deterministic pandas/NumPy calculations
  scanner/           Filters, strategies and ranking
  backtest/          Event-driven historical simulator
supabase/migrations/ Database schema and constraints
tests/               Python, API and UI tests
```

## Next milestones

1. Add the Supabase schema and server configuration.
2. Add a validated market-data provider adapter.
3. Implement deterministic indicators, strategies and scanner ranking.
4. Connect validated scanner results to the dashboard.
5. Add S&P 500/Nasdaq 100 universe presets and optional alerts later.

The V1 deployment must be private or protected by an external access-control layer. Credentials stay server-side, and the application will never place live broker orders.
