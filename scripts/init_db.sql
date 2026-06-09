-- =============================================================================
-- World Cup 2026 Pool – Database Initialisation
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New query).
-- Safe to re-run: uses IF NOT EXISTS / OR REPLACE throughout.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid(), crypt()
CREATE EXTENSION IF NOT EXISTS "moddatetime"; -- automatic updated_at triggers

-- ---------------------------------------------------------------------------
-- 1. system_settings
--    Single-row config table (id = 1 always).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.system_settings (
    id              INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),   -- enforce singleton
    draft_status    TEXT NOT NULL DEFAULT 'PRE_DRAFT'
                        CHECK (draft_status IN ('PRE_DRAFT', 'REVEALING', 'COMPLETE')),
    draft_order     jsonb DEFAULT NULL,
    -- Group stage points
    pt_group_1st    INT NOT NULL DEFAULT 15,
    pt_group_2nd    INT NOT NULL DEFAULT 10,
    pt_group_3rd    INT NOT NULL DEFAULT 5,
    pt_group_4th    INT NOT NULL DEFAULT 0,
    -- Knockout round-win points
    pt_r32_win      INT NOT NULL DEFAULT 5,
    pt_r16_win      INT NOT NULL DEFAULT 10,
    pt_qf_win       INT NOT NULL DEFAULT 15,
    pt_sf_win       INT NOT NULL DEFAULT 20,
    pt_final_win    INT NOT NULL DEFAULT 30,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Prevent inserting a second row
CREATE UNIQUE INDEX IF NOT EXISTS system_settings_singleton ON public.system_settings ((1));

-- ---------------------------------------------------------------------------
-- 2. users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.users (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT UNIQUE,
    is_admin    BOOLEAN NOT NULL DEFAULT FALSE,
    is_bot      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS users_email_idx ON public.users (email) WHERE email IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. teams
--    external_id stores the API-Football team ID for fixture mapping.
--    group_letter is NULL until the official group draw is completed.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.teams (
    id              BIGSERIAL PRIMARY KEY,
    country_name    TEXT NOT NULL UNIQUE,
    iso_code        TEXT NOT NULL UNIQUE,
    pot_number      INT  NOT NULL CHECK (pot_number BETWEEN 1 AND 4),
    fifa_rank       INT,
    group_letter    CHAR(1) CHECK (group_letter BETWEEN 'A' AND 'L'),
    external_id     INT UNIQUE,           -- External API team ID
    flag_url        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS teams_pot_idx        ON public.teams (pot_number);
CREATE INDEX IF NOT EXISTS teams_group_idx      ON public.teams (group_letter) WHERE group_letter IS NOT NULL;
CREATE INDEX IF NOT EXISTS teams_external_idx   ON public.teams (external_id)  WHERE external_id  IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 4. picks
--    One row per (user × team) pair; reveal_sequence is the broadcast order.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.picks (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES public.users(id)  ON DELETE CASCADE,
    team_id             BIGINT NOT NULL REFERENCES public.teams(id)  ON DELETE CASCADE,
    reveal_sequence     INT    NOT NULL UNIQUE CHECK (reveal_sequence BETWEEN 1 AND 48),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, team_id)
);

CREATE INDEX IF NOT EXISTS picks_user_idx     ON public.picks (user_id);
CREATE INDEX IF NOT EXISTS picks_team_idx     ON public.picks (team_id);
CREATE INDEX IF NOT EXISTS picks_sequence_idx ON public.picks (reveal_sequence);

-- ---------------------------------------------------------------------------
-- 5. matches
--    external_id = API-Football fixture ID used as the upsert key.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.matches (
    id              BIGSERIAL PRIMARY KEY,
    external_id     INT UNIQUE,          -- API-Football fixture ID (upsert key)
    -- NULL = participant not yet determined (scheduled knockout fixtures)
    home_team_id    BIGINT REFERENCES public.teams(id),
    away_team_id    BIGINT REFERENCES public.teams(id),
    home_score      INT,
    away_score      INT,
    kickoff_time    TIMESTAMPTZ,
    matchday        INT,
    group_letter    CHAR(5),
    stage           TEXT NOT NULL
                        CHECK (stage IN ('GROUP','R32','R16','QF','SF','THIRD','FINAL')),
    status          TEXT NOT NULL DEFAULT 'SCHEDULED'
                        CHECK (status IN ('SCHEDULED','LIVE','FINISHED')),
    home_team_label TEXT,   -- human-readable placeholder, e.g. "Winner Group A"
    away_team_label TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Only enforce uniqueness when both participants are known
    CONSTRAINT different_teams CHECK (
        home_team_id IS NULL
        OR away_team_id IS NULL
        OR home_team_id <> away_team_id
    )
);

CREATE INDEX IF NOT EXISTS matches_stage_idx    ON public.matches (stage);
CREATE INDEX IF NOT EXISTS matches_status_idx   ON public.matches (status);
CREATE INDEX IF NOT EXISTS matches_kickoff_idx  ON public.matches (kickoff_time);
CREATE INDEX IF NOT EXISTS matches_home_idx     ON public.matches (home_team_id);
CREATE INDEX IF NOT EXISTS matches_away_idx     ON public.matches (away_team_id);

-- Auto-update updated_at on every write
CREATE OR REPLACE TRIGGER matches_updated_at
    BEFORE UPDATE ON public.matches
    FOR EACH ROW EXECUTE PROCEDURE moddatetime(updated_at);

-- ---------------------------------------------------------------------------
-- 6. group_standings  (live standings per group, upserted from API)
--    Upsert key: (group_letter, team_id)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.group_standings (
    id              BIGSERIAL PRIMARY KEY,
    group_letter    CHAR(1)  NOT NULL CHECK (group_letter BETWEEN 'A' AND 'L'),
    team_id         BIGINT   REFERENCES public.teams(id),
    position        INT      NOT NULL DEFAULT 0,   -- 1-4 within the group
    played          INT      NOT NULL DEFAULT 0,
    won             INT      NOT NULL DEFAULT 0,
    drawn           INT      NOT NULL DEFAULT 0,
    lost            INT      NOT NULL DEFAULT 0,
    goals_for       INT      NOT NULL DEFAULT 0,
    goals_against   INT      NOT NULL DEFAULT 0,
    goal_difference INT      NOT NULL DEFAULT 0,
    points          INT      NOT NULL DEFAULT 0,   -- soccer standings points
    -- form            TEXT,                          -- e.g. "WWD"
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (group_letter, team_id)
);

CREATE INDEX IF NOT EXISTS gs_group_idx ON public.group_standings (group_letter);
CREATE INDEX IF NOT EXISTS gs_team_idx  ON public.group_standings (team_id);

CREATE OR REPLACE TRIGGER group_standings_updated_at
    BEFORE UPDATE ON public.group_standings
    FOR EACH ROW EXECUTE PROCEDURE moddatetime(updated_at);

-- ---------------------------------------------------------------------------
-- 7. scores  (denormalised scoring cache – rebuilt by scoring_engine.py)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.scores (
    user_id         BIGINT PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    total_points    INT NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER scores_updated_at
    BEFORE UPDATE ON public.scores
    FOR EACH ROW EXECUTE PROCEDURE moddatetime(updated_at);

-- ---------------------------------------------------------------------------
-- Row-Level Security
-- ---------------------------------------------------------------------------

-- system_settings: public read, no client writes
ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "system_settings_public_read" ON public.system_settings;
CREATE POLICY "system_settings_public_read"
    ON public.system_settings FOR SELECT USING (TRUE);

-- users: public read
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_public_read" ON public.users;
CREATE POLICY "users_public_read"
    ON public.users FOR SELECT USING (TRUE);

-- teams: public read
ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "teams_public_read" ON public.teams;
CREATE POLICY "teams_public_read"
    ON public.teams FOR SELECT USING (TRUE);

-- picks: public read
ALTER TABLE public.picks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "picks_public_read" ON public.picks;
CREATE POLICY "picks_public_read"
    ON public.picks FOR SELECT USING (TRUE);

-- matches: public read
ALTER TABLE public.matches ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "matches_public_read" ON public.matches;
CREATE POLICY "matches_public_read"
    ON public.matches FOR SELECT USING (TRUE);

-- group_standings: public read
ALTER TABLE public.group_standings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "group_standings_public_read" ON public.group_standings;
CREATE POLICY "group_standings_public_read"
    ON public.group_standings FOR SELECT USING (TRUE);

-- scores: public read
ALTER TABLE public.scores ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "scores_public_read" ON public.scores;
CREATE POLICY "scores_public_read"
    ON public.scores FOR SELECT USING (TRUE);

-- NOTE: All writes (INSERT/UPDATE/DELETE) go through the service-role key
-- (SUPABASE_SECRET_KEY) which bypasses RLS entirely. No write policies needed
-- for the application layer.

-- ---------------------------------------------------------------------------
-- Seed: system_settings singleton row (idempotent)
-- ---------------------------------------------------------------------------
INSERT INTO public.system_settings (id) VALUES (1)
    ON CONFLICT (id) DO NOTHING;
