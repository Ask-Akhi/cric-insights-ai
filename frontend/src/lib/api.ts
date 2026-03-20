export type AskIntent = 'stats' | 'compare' | 'fantasy' | 'predict' | 'general'
export type AskMode  = 'graph' | 'direct' | 'fallback' | 'grounded'

export interface AskPayload {
  prompt: string
  context?: Record<string, string | number>
  grounded?: boolean
  use_graph?: boolean
}

export interface AskResult {
  answer: string
  intent: AskIntent
  players: string[]
  mode: AskMode
}

export async function callAsk(apiBase: string, payload: AskPayload): Promise<AskResult> {
  const res = await fetch(`${apiBase}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ use_graph: true, ...payload }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  const json = await res.json()
  return {
    answer:  json.answer  ?? '',
    intent:  json.intent  ?? 'general',
    players: json.players ?? [],
    mode:    json.mode    ?? 'graph',
  }
}

export interface PlayerStats {
  player: string
  found: boolean
  batter: {
    total_runs: number
    total_balls: number
    total_matches: number
    strike_rate: number
    average: number
    fours: number
    sixes: number
    runs_per_match: { match: string; runs: number; balls: number }[]
    format_runs: { format: string; runs: number; matches: number }[]
    dismissals: { type: string; count: number }[]
  } | null
  bowler: {
    total_wickets: number
    total_balls: number
    total_matches: number
    economy: number
    average: number
    strike_rate: number
    wickets_per_match: { match: string; wickets: number; economy: number }[]
    format_wickets: { format: string; wickets: number; matches: number }[]
  } | null
}

export async function callPlayerStats(apiBase: string, playerName: string, format?: string): Promise<PlayerStats> {
  const params = format ? `?format=${encodeURIComponent(format)}` : ''
  const res = await fetch(`${apiBase}/api/players/${encodeURIComponent(playerName)}/stats${params}`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// ── Players search ────────────────────────────────────────────────────────────
export async function callPlayerSearch(apiBase: string, q: string): Promise<string[]> {
  const res = await fetch(`${apiBase}/api/players/?q=${encodeURIComponent(q)}&limit=20`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  const json = await res.json()
  return json.players ?? []
}

// ── Match Insights (Cricsheet-backed) ─────────────────────────────────────────
export interface InsightsRequest {
  format: string
  venue: string
  team_a: string
  team_b: string
  squad_a: string[]
  squad_b: string[]
}

export interface PlayerInsight {
  player: string
  stats: {
    avg_vs_opponent: Record<string, number>
    first_innings_avg: number | null
    second_innings_avg: number | null
    venue_avg: Record<string, number>
    expected_runs?: number
    expected_wickets?: number
    venue_factor?: number
    confidence?: string
  }
  expected: {
    expected_runs: number | null
    expected_wickets: number | null
    venue_factor: number | null
    opponent_factor: number | null
    confidence: string
  }
}

export interface InsightsResponse {
  batters: PlayerInsight[]
  bowlers: PlayerInsight[]
}

export async function callInsights(
  apiBase: string,
  req: InsightsRequest,
): Promise<InsightsResponse> {
  const res = await fetch(`${apiBase}/api/insights`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

export async function callVenueSearch(apiBase: string, q: string): Promise<string[]> {
  const res = await fetch(`${apiBase}/api/matches/venues?q=${encodeURIComponent(q)}&limit=15`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  const json = await res.json()
  return json.venues ?? []
}

export async function callTeamSearch(apiBase: string, q: string): Promise<string[]> {
  const res = await fetch(`${apiBase}/api/matches/teams?q=${encodeURIComponent(q)}&limit=15`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  const json = await res.json()
  return json.teams ?? []
}

// ── Venue stats (Cricsheet) ───────────────────────────────────────────────────
export interface VenueStatsData {
  venue: string
  found: boolean
  matches?: number
  avg_first_innings_runs?: number | null
  avg_second_innings_runs?: number | null
  top_scorers?: { batter: string; runs: number }[]
  top_wicket_takers?: { bowler: string; wickets: number }[]
}

export async function callVenueStats(
  apiBase: string,
  venue: string,
  format?: string,
): Promise<VenueStatsData> {
  const params = format ? `?format=${encodeURIComponent(format)}` : ''
  const res = await fetch(`${apiBase}/api/matches/venue/${encodeURIComponent(venue)}${params}`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// ── Head-to-head (Cricsheet) ──────────────────────────────────────────────────
export interface H2HData {
  team_a: string
  team_b: string
  found: boolean
  matches?: number
  wins_a?: number
  wins_b?: number
  top_batters_a?: { batter: string; runs: number }[]
  top_batters_b?: { batter: string; runs: number }[]
  top_bowlers_a?: { bowler: string; wickets: number }[]
  top_bowlers_b?: { bowler: string; wickets: number }[]
}

export async function callH2H(
  apiBase: string,
  teamA: string,
  teamB: string,
  format?: string,
): Promise<H2HData> {
  const params = new URLSearchParams({ team_a: teamA, team_b: teamB })
  if (format) params.set('format', format)
  const res = await fetch(`${apiBase}/api/matches/h2h?${params}`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// ── Recent matches (Cricsheet) ────────────────────────────────────────────────
export interface MatchRow {
  match_id: string
  format: string
  venue: string
  city: string
  start_date: string
  winner: string | null
  toss_winner: string | null
  toss_decision: string | null
}

export async function callRecentMatches(
  apiBase: string,
  format?: string,
  team?: string,
  limit = 20,
): Promise<MatchRow[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (format) params.set('format', format)
  if (team) params.set('team', team)
  const res = await fetch(`${apiBase}/api/matches/?${params}`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  const json = await res.json()
  return json.matches ?? []
}
