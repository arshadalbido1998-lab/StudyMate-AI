create table if not exists public.study_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null check (length(trim(title)) > 0),
  content_type text not null check (content_type in ('summary', 'chat', 'quiz', 'flashcards')),
  content jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists study_history_user_created_at_idx
  on public.study_history (user_id, created_at desc);

create index if not exists study_history_user_type_created_at_idx
  on public.study_history (user_id, content_type, created_at desc);

grant select, insert, update, delete on public.study_history to authenticated;

alter table public.study_history enable row level security;

drop policy if exists "Users can select their own study history"
  on public.study_history;
create policy "Users can select their own study history"
  on public.study_history
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "Users can insert their own study history"
  on public.study_history;
create policy "Users can insert their own study history"
  on public.study_history
  for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "Users can update their own study history"
  on public.study_history;
create policy "Users can update their own study history"
  on public.study_history
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "Users can delete their own study history"
  on public.study_history;
create policy "Users can delete their own study history"
  on public.study_history
  for delete
  to authenticated
  using (auth.uid() = user_id);

create or replace function public.set_study_history_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists study_history_updated_at on public.study_history;
create trigger study_history_updated_at
  before update on public.study_history
  for each row
  execute function public.set_study_history_updated_at();
