-- Trial Reel Agent: everything the jobs remember (spec section "Database schema").
-- Apply with `jta-reels db migrate`. Videos live in R2; this database stores their keys.

create table if not exists source_assets (
  id            text primary key,              -- "ep013", "ep013-short07"
  title         text not null,
  topic_family  text,
  audio_key     text,                          -- R2 key of the aligned voice track
  align_json    jsonb,                         -- phrase -> t0/t1
  duration_s    numeric,
  created_at    timestamptz not null default now()
);

create table if not exists scenes (
  name          text primary key,              -- "not_force", "alongside", "shield"
  module        text not null,                 -- "episodes/013-scenes.js"
  description   text,
  good_for      text[] not null default '{}',  -- words and moods it fits
  portrait_ok   boolean not null default true
);

-- One row per trial reel. Status flow:
--   draft -> ready (passed every gate) -> publishing (IG container saved) -> posted
--   -> graduated -> shipped, or retired. failed_check / failed_publish are dead ends.
create table if not exists reels (
  id              uuid primary key default gen_random_uuid(),
  parent_id       uuid references reels(id),
  source_asset_id text references source_assets(id),
  type            text not null check (type in ('remix', 'new')),
  batch_date      date,                        -- US Eastern day it is meant for / was posted on
  slot            smallint check (slot between 1 and 4),
  voice           text not null default 'paul',
  hook_card       text,
  script          text,
  caption         text not null,
  variables       jsonb not null default '{}', -- topic_family, hook_pattern, first_frame, length_bucket, ...
  video_key       text,                        -- R2 key of the MP4
  ig_container_id text,
  ig_media_id     text unique,
  permalink       text,
  posted_at       timestamptz,
  graduated_at    timestamptz,
  status          text not null default 'draft' check (status in (
                    'draft', 'failed_check', 'ready', 'publishing', 'posted',
                    'graduated', 'shipped', 'retired', 'failed_publish')),
  status_note     text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- A slot on a given day can only ever hold one live reel: the database itself refuses a double post.
create unique index if not exists reels_one_per_slot
  on reels (batch_date, slot)
  where status in ('publishing', 'posted', 'graduated', 'shipped');

create index if not exists reels_status on reels (status);

-- Insights snapshots. at_hours is the bucket (6, 24, 48, 168); age_hours is the reel's real age when read.
create table if not exists metrics (
  id                bigserial primary key,
  reel_id           uuid not null references reels(id),
  at_hours          smallint not null,
  age_hours         numeric not null,
  taken_at          timestamptz not null default now(),
  views             bigint,
  reach             bigint,
  likes             bigint,
  comments          bigint,
  shares            bigint,
  saves             bigint,
  follows           bigint,
  profile_visits    bigint,
  avg_watch_s       numeric,
  total_watch_s     numeric,
  is_shared_to_feed boolean,
  raw               jsonb not null default '{}',
  unique (reel_id, at_hours)
);

create table if not exists scores (
  reel_id       uuid primary key references reels(id),
  score         numeric not null,
  rank_in_batch smallint,
  components    jsonb not null default '{}',
  scored_at     timestamptz not null default now()
);

create table if not exists arms (
  variable      text not null,
  value         text not null,
  n             integer not null default 0,
  mean_score    numeric,
  last_updated  timestamptz not null default now(),
  primary key (variable, value)
);

create table if not exists playbook (
  version     serial primary key,
  rules       text not null,                   -- markdown
  evidence    jsonb not null default '{}',
  created_at  timestamptz not null default now()
);

create table if not exists trend_notes (
  id              bigserial primary key,
  date            date not null,
  rank            smallint,
  source          text not null check (source in ('tiktok_creative_center', 'trending_sounds', 'google_trends', 'comments')),
  term            text not null,
  why             text,
  topic_family    text,
  used_by_reel_id uuid references reels(id)
);

create table if not exists shipments (
  id              bigserial primary key,
  reel_id         uuid not null references reels(id),
  platform        text not null check (platform in ('facebook', 'tiktok', 'youtube')),
  viraly_post_id  text,
  scheduled_at    timestamptz,
  created_at      timestamptz not null default now(),
  unique (reel_id, platform)
);

create table if not exists checks (
  id          bigserial primary key,
  reel_id     uuid not null references reels(id),
  gate        text not null check (gate in ('theology', 'verse', 'vision', 'audio', 'duplicate', 'caption')),
  pass        boolean not null,
  notes       text,
  created_at  timestamptz not null default now()
);

-- Key/value settings so the Analyst (or Matt) can change behaviour without a deploy.
create table if not exists settings (
  key         text primary key,
  value       jsonb not null,
  updated_at  timestamptz not null default now()
);

create table if not exists job_runs (
  id           bigserial primary key,
  job          text not null,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  ok           boolean,
  outcome      text,                           -- posted / skipped:paused / error ...
  error        text,
  cost_usd     numeric,
  detail       jsonb not null default '{}'
);
create index if not exists job_runs_job on job_runs (job, started_at desc);

-- Defaults from the decisions of 9 Nov 2026. "on conflict do nothing" keeps any value already changed.
insert into settings (key, value) values
  ('paused',              'false'),
  ('stopped_jobs',        '[]'),
  ('daily_cap',           '4'),
  ('timezone',            '"America/New_York"'),
  ('slot_times',          '["08:00", "12:00", "16:00", "20:00"]'),
  ('slot_catchup_hours',  '3'),
  ('graduation_strategy', '"MANUAL"'),
  ('graduation_signal',   '"manual"'),        -- becomes "is_shared_to_feed" once Week 1 proves it
  ('bible_translation',   '"KJV"'),
  ('voices',              '{"paul": null}'),
  ('budgets',             '{"elevenlabs_min_chars": 5000, "claude_daily_usd": null, "scraping_monthly_usd": null}'),
  ('insights_buckets',    '[6, 24, 48, 168]'),
  ('insights_unsupported','[]'),
  ('test_plan',           '{"phase": "month1",
                            "vary": ["topic_family", "hook_pattern"],
                            "hold": {"first_frame": "hook_over_action", "length_bucket": "45-60",
                                     "voice": "paul", "caption_style": "statement"},
                            "log_only": ["slot", "source", "trend_note"]}')
on conflict (key) do nothing;
