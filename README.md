# TradePilot

TradePilot is a single-user, cash-only swing-trading workspace. Phase 1 ships a polished dashboard shell with clearly labeled demo data; it does not place orders and does not connect to an AI API or broker.

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

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

Start the API, then use the interactive docs at `http://localhost:8000/docs` and call `POST /api/scanner/run`. You can pass a small symbol list such as `AAPL`, `MSFT`, and `NVDA`, or omit it to use the configured default universe. Signals are labeled as personal-development data and are not trading recommendations.

For the dashboard to call the scanner, run both services in separate terminals:

```bash
# Terminal 1
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# Terminal 2
npm run dev
```

Then open `http://localhost:3000` and click **Run scanner**. The button calls the real FastAPI endpoint and replaces the illustrative opportunity table with the returned signals.

Daily bars are cached in `work/market_data.sqlite3`, which is ignored by Git. The first scan downloads the historical window; later scans refresh only a small recent window and read the rest locally. Delete the cache file only if you intentionally want to rebuild the local history.

## Portfolio setup

Run `supabase/migrations/0002_portfolio.sql` in the Supabase SQL Editor after the initial migration. Then open the **Portfolio** page in the dashboard and enter your account value, available cash, risk settings, and maximum position count. The dashboard's capital panel will use the saved Supabase values instead of demo figures.

## Optional IBKR read-only connection

TradePilot can read account value, available funds, and open positions from a locally running IBKR Trader Workstation session. It does not place orders. Install the backend requirements, start TWS with API socket clients enabled, and use paper-trading port `7497` first. Configure `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, and `IBKR_BASE_CURRENCY` in `backend/.env` if the defaults do not match your setup.

## Planned architecture

```text
app/                 Next.js routes and dashboard UI
components/          Reusable terminal UI primitives
lib/                 Typed client helpers and formatting
backend/             FastAPI application
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
5. Add trade-planner risk calculations, portfolio tracking and backtesting.

The V1 deployment must be private or protected by an external access-control layer. Credentials stay server-side, and the application will never place live broker orders.
