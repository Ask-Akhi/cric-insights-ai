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
  data_sources: string[]   // e.g. ["Cricsheet RAG", "Google Search"]
  latency_ms: number
  rag_cache_hit: boolean
}

/** Structured API error shape returned by backend */
export interface ApiError {
  code: string
  message: string
  detail?: string
}

function parseApiError(status: number, body: string): string {
  try {
    const json = JSON.parse(body)
    if (json?.error?.message) return json.error.message
    if (json?.detail) return json.detail
  } catch { /* not JSON */ }  if (status === 504) return 'Request timed out — the AI is busy. Try a simpler question or disable Live web search.'
  if (status === 503) return 'Request timed out — the AI took too long. Try a shorter question or disable Live web search.'
  if (status === 429) return 'Too many requests — please wait a moment and try again.'
  return `Server error ${status}. Please try again.`
}

export async function callAsk(apiBase: string, payload: AskPayload): Promise<AskResult> {  // 58s client timeout — Railway kills at 60s; backend times out at 52s and returns 503
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 58_000)

  let res: Response
  try {
    res = await fetch(`${apiBase}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ use_graph: true, ...payload }),
      signal: controller.signal,
    })  } catch (err: unknown) {
    clearTimeout(timeoutId)
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Request timed out (>58s). Try a shorter question or disable Live web search.')
    }
    throw new Error('Failed to reach the server. Check your connection or try again.')
  }
  clearTimeout(timeoutId)

  if (!res.ok) {
    const text = await res.text()
    throw new Error(parseApiError(res.status, text))
  }
  const json = await res.json()
  return {
    answer:        json.answer        ?? '',
    intent:        json.intent        ?? 'general',
    players:       json.players       ?? [],
    mode:          json.mode          ?? 'graph',
    data_sources:  json.data_sources  ?? [],
    latency_ms:    json.latency_ms    ?? 0,
    rag_cache_hit: json.rag_cache_hit ?? false,
  }
}

export interface PlayerSearchResult {
  players: string[]
  query: string
  count: number
  sources?: { alias_hits: number; live_hits: number }
}

export async function callPlayerSearch(apiBase: string, q: string): Promise<string[]> {
  if (q.length < 2) return []
  const res = await fetch(`${apiBase}/api/players/search?q=${encodeURIComponent(q)}&limit=10`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  const json = await res.json()
  return json.players ?? []
}

export async function callPlayerSearchFull(apiBase: string, q: string, limit = 10): Promise<PlayerSearchResult> {
  if (q.length < 2) return { players: [], query: q, count: 0 }
  const res = await fetch(`${apiBase}/api/players/search?q=${encodeURIComponent(q)}&limit=${limit}`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// ── Match schedule ────────────────────────────────────────────────────────────
export interface ScheduleMatch {
  match_id: string
  date: string
  venue: string
  city: string
  format: string
  competition: string
  team1: string
  team2: string
}

export async function callSchedule(
  apiBase: string,
  format?: string,
  daysAhead = 30,
): Promise<ScheduleMatch[]> {
  const params = new URLSearchParams({ days_ahead: String(daysAhead) })
  if (format) params.set('format', format)
  const res = await fetch(`${apiBase}/api/matches/schedule?${params}`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  const json = await res.json()
  return json.schedule ?? []
}

// ── Player stats ──────────────────────────────────────────────────────────────
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

/**
 * Detect player names in a free-text sentence using the backend PLAYER_ALIASES map.
 * O(n) — no Cricsheet I/O. Used by AskAI for real-time chart pre-loading.
 */
export async function callPlayerDetect(apiBase: string, text: string): Promise<string[]> {
  const res = await fetch(`${apiBase}/api/players/detect?text=${encodeURIComponent(text)}`)
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
