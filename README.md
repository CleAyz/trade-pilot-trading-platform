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
