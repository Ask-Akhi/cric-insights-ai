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
