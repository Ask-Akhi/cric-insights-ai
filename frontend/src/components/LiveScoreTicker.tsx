/**
 * LiveScoreTicker — horizontal scrolling live/recent match scores.
 * Uses Cricsheet recent matches from the backend.
 * Falls back to placeholder cards if API is unavailable.
 */
import { useEffect, useState } from 'react'

interface Match {
  match_id?: string
  teams?: string[]
  team1?: string
  team2?: string
  winner?: string
  date?: string
  venue?: string
  format?: string
  score?: string
  status?: 'live' | 'recent' | 'upcoming'
}

interface Props {
  apiBase: string
  format: string
}

// Placeholder matches shown while loading or on error
const PLACEHOLDER: Match[] = [
  { team1: 'India', team2: 'Australia', winner: 'India', format: 'T20', venue: 'Wankhede', status: 'recent', score: 'IND 187/4 (20) · AUS 165/8 (20)' },
  { team1: 'CSK', team2: 'MI', winner: 'CSK', format: 'IPL', venue: 'Chepauk', status: 'recent', score: 'CSK 192/3 (20) · MI 178/6 (20)' },
  { team1: 'RCB', team2: 'KKR', winner: 'KKR', format: 'IPL', venue: 'Eden Gardens', status: 'recent', score: 'KKR 201/5 (20) · RCB 196/7 (20)' },
  { team1: 'England', team2: 'Pakistan', winner: 'England', format: 'ODI', venue: "Lord's", status: 'recent', score: 'ENG 312/6 (50) · PAK 278/9 (50)' },
  { team1: 'SRH', team2: 'DC', winner: 'SRH', format: 'IPL', venue: 'Rajiv Gandhi', status: 'recent', score: 'SRH 215/4 (20) · DC 198/7 (20)' },
]

function statusDot(status?: string) {
  if (status === 'live') return <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse flex-shrink-0" />
  if (status === 'upcoming') return <span className="w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0" />
  return <span className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />
}

export default function LiveScoreTicker({ apiBase, format }: Props) {
  const [matches, setMatches] = useState<Match[]>(PLACEHOLDER)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const url = `${apiBase}/api/matches/recent?format=${format}&limit=8`
    fetch(url)
      .then(r => r.json())
      .then(data => {
        const list: Match[] = Array.isArray(data?.matches) ? data.matches : Array.isArray(data) ? data : []
        if (list.length > 0) setMatches(list)
      })
      .catch(() => { /* keep placeholder */ })
      .finally(() => setLoading(false))
  }, [apiBase, format])

  return (
    <div className="border-b border-white/[0.05]" style={{ background: 'rgba(255,255,255,0.015)' }}>
      <div className="max-w-screen-xl mx-auto px-4 py-2 flex items-center gap-3 overflow-hidden">
        {/* Label */}
        <div className="flex-shrink-0 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-red-400">Live</span>
          <span className="text-[10px] text-slate-600 hidden sm:inline">/ Recent</span>
        </div>
        <div className="w-px h-4 flex-shrink-0" style={{ background: 'rgba(255,255,255,0.08)' }} />

        {/* Scrolling ticker */}
        <div className="flex-1 overflow-x-auto scrollbar-hide">
          <div className="flex gap-3 pb-0.5" style={{ minWidth: 'max-content' }}>
            {(loading ? PLACEHOLDER : matches).map((m, i) => {
              const t1 = m.team1 ?? m.teams?.[0] ?? '?'
              const t2 = m.team2 ?? m.teams?.[1] ?? '?'
              const won = m.winner
              return (
                <div
                  key={m.match_id ?? i}
                  className="flex items-center gap-2 px-3 py-1 rounded-lg flex-shrink-0 text-[11px]"
                  style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
                >
                  {statusDot(m.status)}
                  <span className={`font-semibold ${won === t1 ? 'text-green-400' : 'text-slate-300'}`}>{t1}</span>
                  <span className="text-slate-600">vs</span>
                  <span className={`font-semibold ${won === t2 ? 'text-green-400' : 'text-slate-300'}`}>{t2}</span>
                  {m.score && (
                    <>
                      <span className="text-slate-700">·</span>
                      <span className="text-slate-500 text-[10px]">{m.score}</span>
                    </>
                  )}
                  {won && !m.score && (
                    <>
                      <span className="text-slate-700">·</span>
                      <span className="text-green-400 text-[10px] font-medium">{won} won</span>
                    </>
                  )}
                  {m.format && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded font-bold text-orange-400"
                      style={{ background: 'rgba(255,107,53,0.1)', border: '1px solid rgba(255,107,53,0.15)' }}>
                      {m.format}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
