-- Manual single-user portfolio data. Apply after 0001_initial.sql.

create table if not exists public.portfolio_accounts (
  id text primary key,
  base_currency text not null default 'SGD',
  account_value numeric(16, 2) not null default 0,
  available_cash numeric(16, 2) not null default 0,
  risk_per_trade numeric(6, 3) not null default 0.5,
  max_position_allocation numeric(6, 3) not null default 20,
  max_positions integer not null default 4,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.positions (
  id uuid primary key default gen_random_uuid(),
  account_id text not null references public.portfolio_accounts(id) on delete cascade,
  ticker text not null,
  quantity numeric(16, 6) not null,
  average_price numeric(16, 6) not null,
  currency text not null default 'USD',
  planned_risk numeric(16, 2) not null default 0,
  style text not null default 'swing',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint positions_quantity_positive check (quantity > 0),
  constraint positions_average_price_positive check (average_price > 0)
);

create index if not exists positions_account_id_idx on public.positions(account_id);
alter table public.portfolio_accounts enable row level security;
alter table public.positions enable row level security;
