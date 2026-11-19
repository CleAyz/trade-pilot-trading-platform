-- Persistent scanner history and manual research watchlist.
create table if not exists public.signal_history (
  id uuid primary key default gen_random_uuid(),
  fingerprint text not null unique,
  ticker text not null,
  setup text not null,
  score numeric(6, 3) not null,
  price numeric(14, 4) not null,
  entry_price numeric(14, 4) not null,
  stop_loss numeric(14, 4) not null,
  target_price numeric(14, 4) not null,
  risk_reward numeric(8, 3) not null,
  explanation text not null default '',
  relative_volume numeric(8, 3) not null default 0,
  source text not null default 'unknown',
  signal_date date,
  scanned_at timestamptz not null default now(),
  reviewed_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists signal_history_scanned_at_idx on public.signal_history (scanned_at desc);
create index if not exists signal_history_unread_idx on public.signal_history (reviewed_at) where reviewed_at is null;

create table if not exists public.watchlist_items (
  id uuid primary key default gen_random_uuid(),
  ticker text not null unique,
  signal_id uuid references public.signal_history(id) on delete set null,
  notes text not null default '',
  status text not null default 'watching',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint watchlist_status_check check (status in ('watching', 'triggered', 'invalidated', 'archived'))
);
create index if not exists watchlist_updated_at_idx on public.watchlist_items (updated_at desc);
alter table public.signal_history enable row level security;
alter table public.watchlist_items enable row level security;
