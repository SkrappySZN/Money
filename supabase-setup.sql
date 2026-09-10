-- Money — one row per person, the whole ledger as a JSON document.
-- Paste this into the SQL Editor and hit Run.

create table if not exists public.ledger (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  data       jsonb       not null,
  version    bigint      not null default 1,
  updated_at timestamptz not null default now(),
  device     text
);

alter table public.ledger enable row level security;

-- You can only ever see or touch your own row. Nobody else's is reachable,
-- including with the publishable key that ships in the public page.
drop policy if exists ledger_select_own on public.ledger;
drop policy if exists ledger_insert_own on public.ledger;
drop policy if exists ledger_update_own on public.ledger;
drop policy if exists ledger_delete_own on public.ledger;

create policy ledger_select_own on public.ledger
  for select using (auth.uid() = user_id);
create policy ledger_insert_own on public.ledger
  for insert with check (auth.uid() = user_id);
create policy ledger_update_own on public.ledger
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy ledger_delete_own on public.ledger
  for delete using (auth.uid() = user_id);

-- Signed-in users work through the policies above; anonymous callers get nothing.
grant select, insert, update, delete on public.ledger to authenticated;
revoke all on public.ledger from anon;
