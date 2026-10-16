-- TradePilot V1 foundation. Apply this in Supabase SQL Editor.
-- No auth or user tables are used: this is a single-user application.

create extension if not exists pgcrypto;

create table if not exists public.system_config (
  key text primary key,
  value jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.instruments (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  name text,
  exchange text,
  asset_type text not null default 'common_stock',
  sector text,
  industry text,
  is_active boolean not null default true,
  source text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint instruments_symbol_unique unique (symbol)
);

create table if not exists public.scanner_runs (
  id uuid primary key default gen_random_uuid(),
  trading_date date not null,
  universe_key text not null,
  config_hash text not null,
  strategy_version text not null,
  status text not null default 'started',
  scanned_count integer not null default 0,
  qualified_count integer not null default 0,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  error_message text,
  created_at timestamptz not null default now(),
  constraint scanner_runs_status_check check (status in ('started', 'completed', 'failed', 'incomplete')),
  constraint scanner_runs_idempotency unique (trading_date, universe_key, config_hash, strategy_version)
);

create index if not exists scanner_runs_trading_date_idx on public.scanner_runs (trading_date desc);

create table if not exists public.signals (
  id uuid primary key default gen_random_uuid(),
  scanner_run_id uuid not null references public.scanner_runs(id) on delete cascade,
  instrument_id uuid not null references public.instruments(id),
  strategy_key text not null,
  signal_date date not null,
  score numeric(6, 3),
  current_price numeric(14, 4),
  entry_trigger numeric(14, 4),
  stop_loss numeric(14, 4),
  profit_target numeric(14, 4),
  reward_risk numeric(8, 3),
  relative_volume numeric(8, 3),
  explanation jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint signals_strategy_check check (strategy_key in ('momentum_breakout', 'pullback_uptrend', 'breakout_retest')),
  constraint signals_run_instrument_strategy_unique unique (scanner_run_id, instrument_id, strategy_key)
);

create index if not exists signals_signal_date_idx on public.signals (signal_date desc);
create index if not exists signals_score_idx on public.signals (score desc);

-- Keep private tables closed to the browser. The server-side secret key may access them.
alter table public.system_config enable row level security;
alter table public.instruments enable row level security;
alter table public.scanner_runs enable row level security;
alter table public.signals enable row level security;
