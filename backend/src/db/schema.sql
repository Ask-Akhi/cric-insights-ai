-- Cricket Insights AI — PostgreSQL schema
-- Run once against your Supabase / Neon database.
-- Requires: CREATE EXTENSION IF NOT EXISTS vector;  (pgvector)

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Tables ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS player_season_stats (
    player          TEXT        NOT NULL,
    team            TEXT        NOT NULL,
    season          TEXT        NOT NULL,
    format          TEXT        NOT NULL,
    -- batting
    bat_matches     INTEGER     NOT NULL DEFAULT 0,
    runs            INTEGER     NOT NULL DEFAULT 0,
    balls_faced     INTEGER     NOT NULL DEFAULT 0,
    fours           INTEGER     NOT NULL DEFAULT 0,
    sixes           INTEGER     NOT NULL DEFAULT 0,
    avg             NUMERIC(7,2),
    strike_rate     NUMERIC(7,2),
    -- bowling
    bowl_matches    INTEGER     NOT NULL DEFAULT 0,
    wickets         INTEGER     NOT NULL DEFAULT 0,
    balls_bowled    INTEGER     NOT NULL DEFAULT 0,
    runs_conceded   INTEGER     NOT NULL DEFAULT 0,
    economy         NUMERIC(6,2),
    bowling_avg     NUMERIC(7,2),
    bowling_sr      NUMERIC(7,2),
    PRIMARY KEY (player, team, season, format)
);

CREATE TABLE IF NOT EXISTS head_to_head_summary (
    team_a                  TEXT    NOT NULL,
    team_b                  TEXT    NOT NULL,
    format                  TEXT    NOT NULL,
    team_a_wins             INTEGER NOT NULL DEFAULT 0,
    team_b_wins             INTEGER NOT NULL DEFAULT 0,
    no_result               INTEGER NOT NULL DEFAULT 0,
    total_matches           INTEGER NOT NULL DEFAULT 0,
    last_played             TEXT,
    recent_results_json     TEXT,
    PRIMARY KEY (team_a, team_b, format)
);

CREATE TABLE IF NOT EXISTS match_summary (
    match_id        TEXT        PRIMARY KEY,
    date            TEXT,
    format          TEXT,
    competition     TEXT,
    team_a          TEXT,
    team_b          TEXT,
    venue           TEXT,
    winner          TEXT,
    margin          TEXT,
    summary         TEXT        NOT NULL DEFAULT '',
    embedding       vector(1536)                    -- text-embedding-3-small / gemini-embedding-001
);

CREATE TABLE IF NOT EXISTS recent_form (
    id              SERIAL      PRIMARY KEY,
    team            TEXT        NOT NULL,
    match_id        TEXT        NOT NULL,
    date            TEXT,
    format          TEXT,
    opponent        TEXT        NOT NULL DEFAULT '',
    venue           TEXT,
    result          TEXT,       -- 'won' | 'lost' | 'no result'
    margin          TEXT
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_pss_player  ON player_season_stats (player);
CREATE INDEX IF NOT EXISTS idx_pss_team    ON player_season_stats (team);
CREATE INDEX IF NOT EXISTS idx_pss_format  ON player_season_stats (format);
CREATE INDEX IF NOT EXISTS idx_h2h_teams   ON head_to_head_summary (team_a, team_b);
CREATE INDEX IF NOT EXISTS idx_rf_team     ON recent_form (team);
CREATE INDEX IF NOT EXISTS idx_rf_date     ON recent_form (date DESC);
CREATE INDEX IF NOT EXISTS idx_ms_date     ON match_summary (date DESC);

-- pgvector cosine index (HNSW — fast approximate nearest neighbour)
CREATE INDEX IF NOT EXISTS idx_ms_embedding
    ON match_summary USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search index for fallback when embeddings are not yet populated
CREATE INDEX IF NOT EXISTS idx_ms_fts
    ON match_summary USING gin (to_tsvector('english', summary));

-- ── Convenience views ─────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_top_batters AS
SELECT player, team, season, format, runs, avg, strike_rate, bat_matches
FROM player_season_stats
WHERE runs > 0
ORDER BY runs DESC;

CREATE OR REPLACE VIEW v_top_bowlers AS
SELECT player, team, season, format, wickets, economy, bowling_avg, bowl_matches
FROM player_season_stats
WHERE wickets > 0
ORDER BY wickets DESC;

-- ── Phase 2: deeper analytical tables ─────────────────────────────────────────

-- Pre-aggregated venue stats (fast lookup, avoids match_summary scan).
CREATE TABLE IF NOT EXISTS venue_stats_agg (
    venue               TEXT        NOT NULL,
    format              TEXT        NOT NULL,
    total_matches       INTEGER     NOT NULL DEFAULT 0,
    avg_first_innings   NUMERIC(7,2),
    avg_second_innings  NUMERIC(7,2),
    toss_win_pct        NUMERIC(5,2),
    chase_win_pct       NUMERIC(5,2),
    bat_first_win_pct   NUMERIC(5,2),
    highest_total       INTEGER,
    lowest_total        INTEGER,
    last_played         TEXT,
    top_scorers_json    TEXT,
    top_wicket_takers_json TEXT,
    PRIMARY KEY (venue, format)
);
CREATE INDEX IF NOT EXISTS idx_vsa_venue ON venue_stats_agg (venue);

-- Batter x Bowler head-to-head.
CREATE TABLE IF NOT EXISTS batter_vs_bowler (
    batter          TEXT        NOT NULL,
    bowler          TEXT        NOT NULL,
    format          TEXT        NOT NULL,
    balls           INTEGER     NOT NULL DEFAULT 0,
    runs            INTEGER     NOT NULL DEFAULT 0,
    dismissals      INTEGER     NOT NULL DEFAULT 0,
    fours           INTEGER     NOT NULL DEFAULT 0,
    sixes           INTEGER     NOT NULL DEFAULT 0,
    strike_rate     NUMERIC(7,2),
    avg             NUMERIC(7,2),
    PRIMARY KEY (batter, bowler, format)
);
CREATE INDEX IF NOT EXISTS idx_bvb_batter ON batter_vs_bowler (batter);
CREATE INDEX IF NOT EXISTS idx_bvb_bowler ON batter_vs_bowler (bowler);

-- Player performance at each venue.
CREATE TABLE IF NOT EXISTS player_venue_stats (
    player          TEXT        NOT NULL,
    venue           TEXT        NOT NULL,
    format          TEXT        NOT NULL,
    innings         INTEGER     NOT NULL DEFAULT 0,
    runs            INTEGER     NOT NULL DEFAULT 0,
    balls_faced     INTEGER     NOT NULL DEFAULT 0,
    avg             NUMERIC(7,2),
    strike_rate     NUMERIC(7,2),
    wickets         INTEGER     NOT NULL DEFAULT 0,
    balls_bowled    INTEGER     NOT NULL DEFAULT 0,
    runs_conceded   INTEGER     NOT NULL DEFAULT 0,
    economy         NUMERIC(6,2),
    PRIMARY KEY (player, venue, format)
);
CREATE INDEX IF NOT EXISTS idx_pvs_player ON player_venue_stats (player);
CREATE INDEX IF NOT EXISTS idx_pvs_venue  ON player_venue_stats (venue);

-- Rolling last-N-innings form per player.
CREATE TABLE IF NOT EXISTS player_form_recent (
    player          TEXT        NOT NULL,
    format          TEXT        NOT NULL,
    last_n          INTEGER     NOT NULL DEFAULT 10,
    innings         INTEGER     NOT NULL DEFAULT 0,
    runs            INTEGER     NOT NULL DEFAULT 0,
    balls_faced     INTEGER     NOT NULL DEFAULT 0,
    avg             NUMERIC(7,2),
    strike_rate     NUMERIC(7,2),
    fifties         INTEGER     NOT NULL DEFAULT 0,
    hundreds        INTEGER     NOT NULL DEFAULT 0,
    wickets         INTEGER     NOT NULL DEFAULT 0,
    economy         NUMERIC(6,2),
    updated_at      TEXT,
    PRIMARY KEY (player, format)
);
CREATE INDEX IF NOT EXISTS idx_pfr_player ON player_form_recent (player);


-- Phase 3: cricket news (RSS-driven injury/playing-XI/toss hints for RAG) --
CREATE TABLE IF NOT EXISTS news_items (
    url             TEXT        PRIMARY KEY,
    title           TEXT        NOT NULL,
    summary         TEXT,
    source          TEXT,
    published_at    TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tags            TEXT[]
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_items (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_tags      ON news_items USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_news_fts
    ON news_items USING gin (to_tsvector('english', title || ' ' || COALESCE(summary, '')));
