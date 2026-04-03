-- Inquiry Framework - Supabase/Postgres schema
-- Run this in your Supabase SQL editor to set up the database.

-- -----------------------------------------------------------------------
-- Inquiries: top-level record for each run
-- -----------------------------------------------------------------------
create table if not exists inquiries (
  id                       text primary key,          -- 8-char UUID prefix from engine
  title                    text not null,
  question                 text not null,
  format                   text not null default 'debate',
  status                   text not null default 'planning',  -- planning|running|completed|failed
  config                   jsonb,                     -- full InquiryConfig JSON
  output_dir               text,                      -- filesystem path (engine side)
  -- grounding document: either inline text or a URL/label pointing to the original source
  grounding_document       text,                      -- full text content (embedded inline)
  grounding_document_label text,                      -- human-readable label, e.g. file name or URL
  error                    text,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

-- -----------------------------------------------------------------------
-- Planning sessions: conversation history with the planning agent
-- -----------------------------------------------------------------------
create table if not exists planning_sessions (
  id          uuid primary key default gen_random_uuid(),
  inquiry_id  text references inquiries(id) on delete cascade,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists planning_messages (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references planning_sessions(id) on delete cascade,
  role        text not null check (role in ('user', 'assistant')),
  content     text not null,
  created_at  timestamptz not null default now()
);

create index if not exists planning_messages_session_id_idx
  on planning_messages(session_id, created_at);

-- -----------------------------------------------------------------------
-- Citation verifications: one row per verified citation
-- -----------------------------------------------------------------------
create table if not exists citation_verifications (
  id              uuid primary key default gen_random_uuid(),
  inquiry_id      text not null references inquiries(id) on delete cascade,
  citation_id     text not null,         -- e.g. R1_EC_001
  participant_id  text not null,
  round_key       text not null,
  claim           text,
  source          text,
  verdict         text not null,         -- VERIFIED|FABRICATED|NEEDS_REVIEW|UNVERIFIABLE
  pass1_result    text,
  pass2_result    text,
  pass3_result    text,
  notes           text,
  created_at      timestamptz not null default now()
);

create index if not exists citation_verifications_inquiry_id_idx
  on citation_verifications(inquiry_id);

-- Index on source enables cross-inquiry queries:
-- "has this source been flagged before?"
create index if not exists citation_verifications_source_idx
  on citation_verifications(source);

-- -----------------------------------------------------------------------
-- Post-inquiry chat sessions (Phase 3)
-- -----------------------------------------------------------------------
create table if not exists analysis_sessions (
  id             uuid primary key default gen_random_uuid(),
  inquiry_id     text not null references inquiries(id) on delete cascade,
  mode           text not null default 'analysis',  -- analysis|participant
  participant_id text,                   -- set for 1:1 participant chats
  created_at     timestamptz not null default now()
);

create table if not exists analysis_messages (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references analysis_sessions(id) on delete cascade,
  role        text not null check (role in ('user', 'assistant')),
  content     text not null,
  created_at  timestamptz not null default now()
);

create index if not exists analysis_messages_session_id_idx
  on analysis_messages(session_id, created_at);

-- -----------------------------------------------------------------------
-- Updated_at triggers
-- -----------------------------------------------------------------------
create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger inquiries_updated_at
  before update on inquiries
  for each row execute function update_updated_at();

create trigger planning_sessions_updated_at
  before update on planning_sessions
  for each row execute function update_updated_at();
