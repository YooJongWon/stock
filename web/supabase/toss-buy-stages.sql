-- Run once in the Supabase SQL Editor before deploying Toss buy-stage syncing.
create table if not exists public.private_toss_buy_stages (
  holding_key text primary key check (length(holding_key) between 1 and 120),
  stage smallint not null check (stage in (1, 2))
);

alter table public.private_toss_buy_stages enable row level security;
revoke all on table public.private_toss_buy_stages from anon, authenticated;
grant select, insert, update on table public.private_toss_buy_stages to service_role;
