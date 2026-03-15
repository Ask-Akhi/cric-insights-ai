import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import MatchForm, { MatchFormData } from './MatchForm'
import { callInsights, callAsk, InsightsResponse, PlayerInsight } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

// ── Confidence badge ─────────────────────────────────────────────────────────
function ConfBadge({ conf }: { conf: string }) {
  const colors: Record<string, string> = {
    high:   'text-green-400 bg-green-500/10 border-green-500/20',
    medium: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    low:    'text-slate-500 bg-slate-500/10 border-slate-500/20',
  }
  return (
    <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full border ${colors[conf] ?? colors.low}`}>
      {conf}
    </span>
  )
}

// ── Single player card ───────────────────────────────────────────────────────
function PlayerCard({ p, role }: { p: PlayerInsight; role: 'bat' | 'bowl' }) {
  const exp   = p.expected
  const isBat = role === 'bat'
  const val   = isBat ? exp.expected_runs : exp.expected_wickets
  const label = isBat ? 'Exp. Runs' : 'Exp. Wkts'
  const vf    = exp.venue_factor
  const of    = exp.opponent_factor
  const noData = val === null && (vf === null || vf === 1) && (of === null || of === 1)

  return (
    <div
      className="flex items-center gap-3 px-4 py-3 rounded-xl transition-colors"
      style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}
    >
      {/* Avatar */}
      <div
        className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0"
        style={{ background: isBat ? 'rgba(255,107,53,0.15)' : 'rgba(245,200,66,0.15)' }}
      >
        {p.player.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
      </div>

      {/* Name */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-slate-100 truncate">{p.player}</p>
        {noData
          ? <p className="text-[10px] text-slate-600 mt-0.5">No Cricsheet data</p>
          : (
            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
              {vf !== null && <span className="text-[10px] text-slate-500">Venue ×{vf?.toFixed(2)}</span>}
              {of !== null && <span className="text-[10px] text-slate-500">vs ×{of?.toFixed(2)}</span>}
            </div>
          )
        }
      </div>

      {/* Expected value */}
      {!noData && val !== null && (
        <div className="text-right flex-shrink-0">
          <p className="text-lg font-bold" style={{ color: isBat ? '#ff6b35' : '#f5c842' }}>
            {val}
          </p>
          <p className="text-[9px] text-slate-600 uppercase tracking-wide">{label}</p>
        </div>
      )}

      {/* Confidence */}
      {!noData && <ConfBadge conf={exp.confidence} />}
    </div>
  )
}

// ── Team panel ───────────────────────────────────────────────────────────────
function TeamPanel({
  team, players, role,
}: { team: string; players: PlayerInsight[]; role: 'bat' | 'bowl' }) {
  const sorted = [...players].sort((a, b) => {
    const av = role === 'bat' ? (a.expected.expected_runs ?? -1) : (a.expected.expected_wickets ?? -1)
    const bv = role === 'bat' ? (b.expected.expected_runs ?? -1) : (b.expected.expected_wickets ?? -1)
    return bv - av
  })

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest px-1">{team}</h4>
      {sorted.map(p => <PlayerCard key={p.player} p={p} role={role} />)}
    </div>
  )
}

// ── Fantasy picks derived from data ─────────────────────────────────────────
function FantasyPicks({ data }: { data: InsightsResponse }) {
  const topBat = [...data.batters]
    .filter(p => p.expected.expected_runs !== null)
    .sort((a, b) => (b.expected.expected_runs ?? 0) - (a.expected.expected_runs ?? 0))
    .slice(0, 3)

  const topBowl = [...data.bowlers]
    .filter(p => p.expected.expected_wickets !== null)
    .sort((a, b) => (b.expected.expected_wickets ?? 0) - (a.expected.expected_wickets ?? 0))
    .slice(0, 3)

  if (!topBat.length && !topBowl.length) return null

  return (
    <div
      className="p-5 rounded-2xl space-y-3"
      style={{ background: 'rgba(255,107,53,0.05)', border: '1px solid rgba(255,107,53,0.15)' }}
    >
      <p className="text-xs font-bold uppercase tracking-widest text-orange-400">⚡ Fantasy Picks · From Cricsheet Data</p>
      <div className="grid grid-cols-2 gap-4">
        {topBat.length > 0 && (
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-2">Top Batters</p>
            {topBat.map((p, i) => (
              <div key={p.player} className="flex items-center gap-2 mb-1.5">
                <span className="text-[10px] font-bold text-slate-600 w-3">{i + 1}</span>
                <span className="text-xs text-slate-200 flex-1 truncate">{p.player}</span>
                <span className="text-xs font-bold text-orange-400">{p.expected.expected_runs}</span>
              </div>
            ))}
          </div>
        )}
        {topBowl.length > 0 && (
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-2">Top Bowlers</p>
            {topBowl.map((p, i) => (
              <div key={p.player} className="flex items-center gap-2 mb-1.5">
                <span className="text-[10px] font-bold text-slate-600 w-3">{i + 1}</span>
                <span className="text-xs text-slate-200 flex-1 truncate">{p.player}</span>
                <span className="text-xs font-bold text-amber-400">{p.expected.expected_wickets}w</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function Insights({ apiBase, format, grounded }: Props) {
  const [form, setForm] = useState<MatchFormData>({
    format, teamA: '', teamB: '', venue: '', matchDate: '', squadA: [], squadB: [],
  })
  const [loading, setLoading]   = useState(false)
  const [aiLoading, setAiLoad]  = useState(false)
  const [data, setData]         = useState<InsightsResponse | null>(null)
  const [aiAnswer, setAiAnswer] = useState<string | null>(null)
  const [error, setError]       = useState<string | null>(null)
  const [tab, setTab]           = useState<'data' | 'ai'>('data')
  const splitSquad = (s: string[]) => s.filter(Boolean)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.teamA || !form.teamB || !form.venue) return
    setError(null)
    setData(null)
    setAiAnswer(null)

    const squadA = splitSquad(form.squadA)
    const squadB = splitSquad(form.squadB)

    // Fire both requests in parallel
    setLoading(true)
    setAiLoad(true)

    const insightsReq = callInsights(apiBase, {
      format: form.format,
      venue: form.venue,
      team_a: form.teamA,
      team_b: form.teamB,
      squad_a: squadA,
      squad_b: squadB,
    })

    const aiReq = callAsk(apiBase, {
      prompt:
        `Analyse the upcoming ${form.format} match: ${form.teamA} vs ${form.teamB} at ${form.venue}` +
        (form.matchDate ? ` on ${form.matchDate}` : '') + '.\n' +
        (squadA.length ? `${form.teamA} squad: ${squadA.join(', ')}\n` : '') +
        (squadB.length ? `${form.teamB} squad: ${squadB.join(', ')}\n` : '') +
        `Provide: 1) Team form & strengths 2) Key player matchups 3) Pitch & conditions ` +
        `4) Predicted Playing XI (both teams) 5) Top fantasy picks with captain/VC 6) Match prediction with probability.`,
      context: {
        format: form.format, venue: form.venue,
        team_a: form.teamA, team_b: form.teamB,
      },
      grounded,
    })

    insightsReq
      .then(setData)
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false))

    aiReq
      .then(setAiAnswer)
      .catch(() => setAiAnswer(null))
      .finally(() => setAiLoad(false))
  }

  const hasAnyData = data && (data.batters.length > 0 || data.bowlers.length > 0)
  const squadAPlayers = form.squadA
  const squadBPlayers = form.squadB

  const battersA = data?.batters.filter(p => squadAPlayers.includes(p.player)) ?? []
  const battersB = data?.batters.filter(p => squadBPlayers.includes(p.player)) ?? []
  const bowlersA = data?.bowlers.filter(p => squadAPlayers.includes(p.player)) ?? []
  const bowlersB = data?.bowlers.filter(p => squadBPlayers.includes(p.player)) ?? []

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex items-start gap-4">
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl flex-shrink-0 animate-float"
          style={{ background: 'linear-gradient(135deg,rgba(255,107,53,.2),rgba(255,85,0,.08))', border: '1px solid rgba(255,107,53,.25)' }}
        >
          📊
        </div>
        <div className="pt-1">
          <h2 className="text-2xl font-bold text-white leading-tight" style={{ fontFamily: '"Playfair Display",Georgia,serif' }}>
            Squad Insights
          </h2>
          <p className="text-sm text-slate-500 mt-1">Cricsheet ball-by-ball stats + AI analysis for your match-up</p>
        </div>
      </div>

      {/* ── Form ── */}
      <form onSubmit={handleSubmit} className="glass-strong p-6 space-y-5">
        <MatchForm apiBase={apiBase} value={form} onChange={setForm} />
        <button
          type="submit"
          disabled={loading || aiLoading || !form.teamA || !form.teamB || !form.venue}
          className="btn-primary w-full"
        >
          {loading || aiLoading ? (
            <><span className="animate-spin mr-2">⏳</span>Analysing…</>
          ) : (
            '📊 Generate Insights'
          )}
        </button>
      </form>

      {error && (
        <div className="glass p-4 text-sm text-red-400 border border-red-500/20 rounded-xl">{error}</div>
      )}

      {/* ── Results ── */}
      <AnimatePresence>
        {(hasAnyData || aiAnswer) && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-5"
          >
            {/* Tab bar */}
            <div
              className="flex gap-2 p-1 rounded-xl w-fit"
              style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}
            >
              <button
                onClick={() => setTab('data')}
                className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'data' ? 'bg-orange-500 text-white' : 'text-slate-400'}`}
              >
                📊 Cricsheet Data
              </button>
              <button
                onClick={() => setTab('ai')}
                className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'ai' ? 'bg-indigo-500 text-white' : 'text-slate-400'}`}
              >
                💬 AI Analysis {aiLoading ? '⏳' : ''}
              </button>
            </div>

            {/* ── DATA TAB ── */}
            {tab === 'data' && (
              <div className="space-y-5">
                {loading && (
                  <div className="glass p-6 space-y-3">
                    <div className="shimmer-line h-4 w-1/3" />
                    <div className="shimmer-line h-3 w-full" />
                    <div className="shimmer-line h-3 w-4/5" />
                  </div>
                )}

                {hasAnyData && (
                  <>
                    <FantasyPicks data={data!} />

                    {/* Batting */}
                    <div className="glass p-5 space-y-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-orange-400">🏏 Batting — Expected Runs</p>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {battersA.length > 0 && <TeamPanel team={form.teamA} players={battersA} role="bat" />}
                        {battersB.length > 0 && <TeamPanel team={form.teamB} players={battersB} role="bat" />}
                        {!battersA.length && !battersB.length && (
                          <p className="text-sm text-slate-500 col-span-2">
                            Enter squad names above to see per-player batting projections from Cricsheet data.
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Bowling */}
                    <div className="glass p-5 space-y-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-amber-400">🎳 Bowling — Expected Wickets</p>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {bowlersA.length > 0 && <TeamPanel team={form.teamA} players={bowlersA} role="bowl" />}
                        {bowlersB.length > 0 && <TeamPanel team={form.teamB} players={bowlersB} role="bowl" />}
                        {!bowlersA.length && !bowlersB.length && (
                          <p className="text-sm text-slate-500 col-span-2">
                            Enter squad names above to see per-player bowling projections from Cricsheet data.
                          </p>
                        )}
                      </div>
                    </div>
                  </>
                )}

                {!loading && !hasAnyData && (
                  <div className="glass p-6 text-sm text-slate-500 text-center">
                    No Cricsheet ball-by-ball data found for the provided squads.
                    The dataset covers matches up to 2016 — add squad names to get projections.
                  </div>
                )}
              </div>
            )}

            {/* ── AI TAB ── */}
            {tab === 'ai' && (
              <div className="glass p-6">
                {aiLoading && (
                  <div className="space-y-3 animate-fade-in">
                    <div className="shimmer-line h-4 w-3/4" />
                    <div className="shimmer-line h-4 w-full" />
                    <div className="shimmer-line h-4 w-5/6" />
                    <div className="shimmer-line h-4 w-2/3 mt-4" />
                    <div className="shimmer-line h-4 w-full" />
                  </div>
                )}                {!aiLoading && aiAnswer && (
                  <div className="prose prose-invert prose-sm max-w-none text-slate-300">
                    <ReactMarkdown>{aiAnswer}</ReactMarkdown>
                  </div>
                )}
                {!aiLoading && !aiAnswer && (
                  <p className="text-sm text-slate-500">AI analysis unavailable.</p>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
