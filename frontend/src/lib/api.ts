export interface AskPayload {
  prompt: string
  context?: Record<string, string | number>
  grounded?: boolean
}

export async function callAsk(apiBase: string, payload: AskPayload): Promise<string> {
  const res = await fetch(`${apiBase}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  const json = await res.json()
  return json.answer ?? JSON.stringify(json)
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

export async function callPlayerStats(apiBase: string, playerName: string): Promise<PlayerStats> {
  const res = await fetch(`${apiBase}/api/players/${encodeURIComponent(playerName)}/stats`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}
