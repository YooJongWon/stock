-- 개인 포트폴리오와 계산기 설정 저장용 테이블
-- Supabase SQL Editor에서 한 번 실행하세요.

create table if not exists public.private_portfolio_data (
  id text primary key default 'owner' check (id = 'owner'),
  cash_balance numeric(20, 4) not null default 0,
  calculator_settings jsonb not null default '{}'::jsonb,
  positions jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.private_portfolio_data enable row level security;

-- 브라우저 anon/authenticated 역할에서 직접 읽거나 수정하지 못하게 합니다.
revoke all on table public.private_portfolio_data from anon, authenticated;
grant all on table public.private_portfolio_data to service_role;

insert into public.private_portfolio_data (id)
values ('owner')
on conflict (id) do nothing;
