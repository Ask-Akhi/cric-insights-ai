/**
 * LiveScoreTicker — horizontal scrolling recent match results.
 * Fetches real Cricsheet data from /api/matches/recent, filtered by format.
 */
import { useEffect, useState } from 'react'

interface Match {
  match_id?: string
  team1?: string
  team2?: string
  score?: string
  winner?: string
  date?: string
  venue?: string
  format?: string
  competition?: string
  status?: string
}

interface ApiResponse {
  matches: Match[]
  count: number
  latest_date?: string
  data_note?: string
  live?: boolean
  source?: string
}

interface Props {
  apiBase: string
  format: string
  onLiveChange?: (isLive: boolean) => void
}

export default function LiveScoreTicker({ apiBase, format, onLiveChange }: Props) {
  const [matches, setMatches] = useState<Match[]>([])
  const [latestDate, setLatestDate] = useState<string>('')
  const [isLive, setIsLive] = useState(false)
  const [source, setSource] = useState('cricsheet')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(false)
    const url = `${apiBase}/api/matches/recent?format=${encodeURIComponent(format)}&limit=12`
    fetch(url)
      .then(r => r.json())      .then((data: ApiResponse) => {
        setMatches(Array.isArray(data?.matches) ? data.matches : [])
        setLatestDate(data?.latest_date ?? '')
        const live = data?.live ?? false
        setIsLive(live)
        setSource(data?.source ?? 'cricsheet')
        onLiveChange?.(live)
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
      <div className="max-w-screen-xl mx-auto px-4 py-2 flex items-center gap-3 overflow-hidden">        {/* Label */}
        <div className="flex-shrink-0 flex items-center gap-1.5">
          {isLive ? (
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-red-500" />
            </span>
          ) : (
            <span className="w-1.5 h-1.5 rounded-full bg-slate-600" />
          )}
          <span className={`text-[10px] font-bold uppercase tracking-widest ${isLive ? 'text-red-400' : 'text-slate-500'}`}>
            {isLive ? source : 'Cricsheet'}
          </span>
          <span className="text-[10px] text-orange-400 font-semibold ml-1">{format}</span>
          {!isLive && latestDate && (
            <span className="text-[9px] text-slate-700 ml-1 hidden sm:inline">
              · up to {latestDate.slice(0, 7)}
            </span>
          )}
          {isLive && (
            <span className="text-[9px] text-green-600 ml-1 hidden sm:inline">· live</span>
          )}
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
          )}          {!loading && !error && matches.length > 0 && (
            <div className="flex gap-3 pb-0.5" style={{ minWidth: 'max-content' }}>
              {matches.map((m, i) => {
                const winner = m.winner || ''
                const t1 = m.team1 || '?'
                const t2 = m.team2 || ''
                const fmt = m.format || ''
                return (
                  <div
                    key={m.match_id ?? i}
                    className="flex items-center gap-2 px-3 py-1 rounded-lg flex-shrink-0 text-[11px]"
                    style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
                  >                    {m.status === 'live' ? (
                      <span className="relative flex h-1.5 w-1.5 flex-shrink-0">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75" />
                        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-red-500" />
                      </span>
                    ) : (
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-600 flex-shrink-0" />
                    )}

                    {/* Team 1 */}
                    <span className={`font-semibold ${winner === t1 ? 'text-green-400' : 'text-slate-300'}`}>
                      {t1}
                    </span>

                    {/* Team 2 */}
                    {t2 && (
                      <>
                        <span className="text-slate-600">vs</span>
                        <span className={`font-semibold ${winner === t2 ? 'text-green-400' : 'text-slate-300'}`}>
                          {t2}
                        </span>
                      </>
                    )}                    {/* Live score OR completed result */}
                    {m.score ? (
                      <>
                        <span className="text-slate-700 text-[9px]">·</span>
                        <span className="text-yellow-400 text-[10px] font-mono truncate max-w-[160px]">{m.score}</span>
                      </>
                    ) : winner ? (
                      <>
                        <span className="text-slate-700 text-[9px]">·</span>
                        <span className="text-green-400 text-[10px] font-medium">{winner} won</span>
                      </>
                    ) : null}

                    {/* Venue — only when no score */}
                    {!m.score && m.venue && (
                      <>
                        <span className="text-slate-700 text-[9px]">·</span>
                        <span className="text-slate-600 text-[10px] max-w-[100px] truncate">{m.venue}</span>
                      </>
                    )}

                    {/* Date */}
                    {m.date && (
                      <span className="text-slate-700 text-[10px]">{shortDate(m.date)}</span>
                    )}

                    {/* Format badge */}
                    {fmt && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded font-bold text-orange-400"
                        style={{ background: 'rgba(255,107,53,0.1)', border: '1px solid rgba(255,107,53,0.15)' }}>
                        {fmt}
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
