/**
 * LiveScoreTicker — horizontal scrolling recent match results.
 * Fetches real Cricsheet data from /api/matches/recent, filtered by format.
 */
import { useEffect, useState } from 'react'

interface Match {
  match_id?: string
  team1?: string
  team2?: string
  winner?: string
  date?: string
  venue?: string
  format?: string
  competition?: string
  status?: string
}

interface Props {
  apiBase: string
  format: string
}

export default function LiveScoreTicker({ apiBase, format }: Props) {
  const [matches, setMatches] = useState<Match[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(false)
    const url = `${apiBase}/api/matches/recent?format=${encodeURIComponent(format)}&limit=12`
    fetch(url)
      .then(r => r.json())
      .then(data => {
        const list: Match[] = Array.isArray(data?.matches) ? data.matches : []
        setMatches(list)
        setLoading(false)
      })
      .catch(() => {
        setError(true)
        setLoading(false)
      })
  }, [apiBase, format])

  // Format a short date string: "12 Mar 2024" → "Mar 2024"
  const shortDate = (d?: string) => {
    if (!d) return ''
    const dt = new Date(d)
    if (isNaN(dt.getTime())) return d
    return dt.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
  }

  const isEmpty = !loading && !error && matches.length === 0

  return (
    <div className="border-b border-white/[0.05]" style={{ background: 'rgba(255,255,255,0.015)' }}>
      <div className="max-w-screen-xl mx-auto px-4 py-2 flex items-center gap-3 overflow-hidden">
        {/* Label */}
        <div className="flex-shrink-0 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Recent
          </span>
          <span className="text-[10px] text-orange-400 font-semibold ml-1">{format}</span>
        </div>
        <div className="w-px h-4 flex-shrink-0" style={{ background: 'rgba(255,255,255,0.08)' }} />

        {/* Ticker content */}
        <div className="flex-1 overflow-x-auto scrollbar-hide">
          {loading && (
            <div className="flex gap-3 pb-0.5" style={{ minWidth: 'max-content' }}>
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-6 w-40 rounded-lg animate-pulse"
                  style={{ background: 'rgba(255,255,255,0.04)' }} />
              ))}
            </div>
          )}

          {error && (
            <span className="text-[10px] text-slate-600">Could not load recent matches</span>
          )}

          {isEmpty && (
            <span className="text-[10px] text-slate-600">No recent {format} matches in dataset</span>
          )}

          {!loading && !error && matches.length > 0 && (
            <div className="flex gap-3 pb-0.5" style={{ minWidth: 'max-content' }}>
              {matches.map((m, i) => {
                const winner = m.winner || ''
                const team1 = m.team1 || '?'
                // Cricsheet stores winner; use it to infer teams where possible
                const isT1Winner = winner && winner === team1
                return (
                  <div
                    key={m.match_id ?? i}
                    className="flex items-center gap-2 px-3 py-1 rounded-lg flex-shrink-0 text-[11px]"
                    style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />

                    {/* Teams */}
                    <span className={`font-semibold ${isT1Winner ? 'text-green-400' : 'text-slate-300'}`}>
                      {team1}
                    </span>

                    {/* Winner badge */}
                    {winner && (
                      <>
                        <span className="text-slate-600 text-[9px]">·</span>
                        <span className="text-green-400 text-[10px] font-medium">{winner} won</span>
                      </>
                    )}

                    {/* Venue */}
                    {m.venue && (
                      <>
                        <span className="text-slate-700 text-[9px]">·</span>
                        <span className="text-slate-600 text-[10px] max-w-[120px] truncate">{m.venue}</span>
                      </>
                    )}

                    {/* Date */}
                    {m.date && (
                      <span className="text-slate-700 text-[10px]">{shortDate(m.date)}</span>
                    )}

                    {/* Format badge */}
                    {m.competition && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded font-bold text-orange-400"
                        style={{ background: 'rgba(255,107,53,0.1)', border: '1px solid rgba(255,107,53,0.15)' }}>
                        {m.competition}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
