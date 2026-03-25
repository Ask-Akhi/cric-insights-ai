import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import SquadBuilder from '../components/SquadBuilder'
import { callPlayerStats, callAsk, PlayerStats } from '../lib/api'
import ReactMarkdown from 'react-markdown'

interface Props { apiBase: string; format: string; grounded: boolean; onQuestionAsked?: () => void }

// ── Fantasy point model (Dream11-like) ───────────────────────────────────────
// Batting: 1 pt/run, 4=1 bonus, 6=2 bonus, 50=8 bonus, 100=16 bonus, S/R bonus
// Bowling: 25 pt/wkt, economy bonus, 3w=4, 4w=8, 5w=16
//
// Form weighting: recent 10 innings count 70%, career average 30%.
// This prevents cold veterans outscoring hot in-form players.
function calcFantasyScore(stats: PlayerStats): number {
  let pts = 0
  const bat = stats.batter
  const bowl = stats.bowler

  if (bat) {
    // Career averages
    const careerRPM = bat.total_runs / Math.max(bat.total_matches, 1)
    const ballsPerMatch = bat.total_balls / Math.max(bat.total_matches, 1)
    const sr = bat.strike_rate

    // Recent form: last 10 entries from runs_per_match array (sorted oldest→newest by API)
    const recent = bat.runs_per_match.slice(-10)
    const recentRPM = recent.length > 0
      ? recent.reduce((s, r) => s + r.runs, 0) / recent.length
      : careerRPM

    // Weighted expected runs per match (70% recent, 30% career)
    const expectedRPM = recent.length >= 3
      ? recentRPM * 0.7 + careerRPM * 0.3
      : careerRPM  // not enough recent data — use career only

    // Run points
    pts += expectedRPM * 1
    // 4s/6s bonus (proportional to career rate — not enough recent granularity)
    pts += (bat.fours / Math.max(bat.total_matches, 1)) * 1
    pts += (bat.sixes / Math.max(bat.total_matches, 1)) * 2
    // Milestone bonus estimated from weighted average
    const weightedAvg = recent.length >= 3
      ? recentRPM * 0.7 + bat.average * 0.3
      : bat.average
    if (weightedAvg >= 50) pts += 16
    else if (weightedAvg >= 25) pts += 8
    // SR bonus
    if (sr >= 170) pts += 6
    else if (sr >= 150) pts += 4
    else if (sr >= 130) pts += 2
    else if (sr < 60 && ballsPerMatch > 4) pts -= 2

    // Form streak bonus: last 3 matches all above career average → +3
    if (recent.length >= 3 && recent.slice(-3).every(r => r.runs >= careerRPM)) pts += 3
  }

  if (bowl) {
    // Career averages
    const careerWPM = bowl.total_wickets / Math.max(bowl.total_matches, 1)

    // Recent form: last 10 entries from wickets_per_match
    const recent = bowl.wickets_per_match.slice(-10)
    const recentWPM = recent.length > 0
      ? recent.reduce((s, r) => s + r.wickets, 0) / recent.length
      : careerWPM
    const recentEcon = recent.length > 0
      ? recent.reduce((s, r) => s + r.economy, 0) / recent.length
      : bowl.economy

    // Weighted expected wickets per match (70% recent, 30% career)
    const expectedWPM = recent.length >= 3
      ? recentWPM * 0.7 + careerWPM * 0.3
      : careerWPM
    const expectedEcon = recent.length >= 3
      ? recentEcon * 0.7 + bowl.economy * 0.3
      : bowl.economy

    // Wicket points
    pts += expectedWPM * 25
    // Economy bonus (on weighted recent economy)
    if (expectedEcon < 6) pts += 6
    else if (expectedEcon < 7) pts += 4
    else if (expectedEcon < 8) pts += 2
    else if (expectedEcon > 10) pts -= 2
    // Multi-wicket haul bonus
    if (expectedWPM >= 3) pts += 8
    else if (expectedWPM >= 2) pts += 4

    // Form streak bonus: last 3 matches all ≥ 1 wicket → +2
    if (recent.length >= 3 && recent.slice(-3).every(r => r.wickets >= 1)) pts += 2
  }

  return Math.round(pts * 10) / 10
}

interface ScoredPlayer {
  name: string
  stats: PlayerStats | null
  score: number
  role: 'bat' | 'bowl' | 'allrounder' | 'unknown'
}

function roleTag(s: PlayerStats | null): ScoredPlayer['role'] {
  if (!s) return 'unknown'
  if (s.batter && s.bowler) return 'allrounder'
  if (s.batter) return 'bat'
  if (s.bowler) return 'bowl'
  return 'unknown'
}

const ROLE_COLOR: Record<string, string> = {
  bat:        'text-orange-400 bg-orange-500/10 border-orange-500/20',
  bowl:       'text-amber-400 bg-amber-500/10 border-amber-500/20',
  allrounder: 'text-green-400 bg-green-500/10 border-green-500/20',
  unknown:    'text-slate-500 bg-slate-500/10 border-slate-500/20',
}
const ROLE_LABEL: Record<string, string> = {
  bat: '🏏 BAT', bowl: '🎳 BOWL', allrounder: '⭐ ALL', unknown: '—',
}

export default function FantasyXI({ apiBase, format, grounded, onQuestionAsked }: Props) {
  const [squad, setSquad] = useState<string[]>([])
  const [players, setPlayers] = useState<ScoredPlayer[] | null>(null)
  const [aiAnswer, setAiAnswer] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'xi' | 'ai'>('xi')
  const [captain, setCaptain] = useState<string | null>(null)
  const [viceCaptain, setViceCaptain] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const names = squad.filter(Boolean)
    if (names.length < 2) return
    setError(null); setPlayers(null); setAiAnswer(null); setCaptain(null); setViceCaptain(null)
    setLoading(true)

    // Fetch all player stats in parallel
    const results = await Promise.allSettled(names.map(n => callPlayerStats(apiBase, n)))
    const scored: ScoredPlayer[] = names.map((name, i) => {
      const r = results[i]
      const stats = r.status === 'fulfilled' ? r.value : null
      const score = stats ? calcFantasyScore(stats) : 0
      return { name: stats?.player ?? name, stats, score, role: roleTag(stats) }
    })
    // Sort descending by score
    scored.sort((a, b) => b.score - a.score)
    setPlayers(scored)
    setCaptain(scored[0]?.name ?? null)
    setViceCaptain(scored[1]?.name ?? null)

    // AI picks in parallel
    callAsk(apiBase, {
      prompt:
        `For a Dream11 fantasy team for a ${format} match, rank these players by fantasy value: ${names.join(', ')}. ` +
        `For each player give: role (bat/bowl/allrounder), expected points range, and risk level. ` +
        `Then pick the best captain, vice-captain, and a differential pick with reasoning.`,
      context: { format, players: names.join(', ') },
      grounded,
    })      .then(r => { setAiAnswer(r.answer); onQuestionAsked?.() })
      .catch(() => setAiAnswer(null))
      .finally(() => setLoading(false))
  }

  const medal = (idx: number) => idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : `${idx + 1}`

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl flex-shrink-0 animate-float"
          style={{ background: 'linear-gradient(135deg,rgba(245,200,66,.2),rgba(255,107,53,.1))', border: '1px solid rgba(245,200,66,.3)' }}
        >
          🏆
        </div>
        <div className="pt-1">
          <h2 className="text-2xl font-bold text-white leading-tight" style={{ fontFamily: '"Playfair Display",Georgia,serif' }}>
            Fantasy XI Builder
          </h2>
          <p className="text-sm text-slate-500 mt-1">Score your squad with AI-powered fantasy picks</p>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="glass-strong p-6 space-y-4">
        <SquadBuilder
          apiBase={apiBase}
          label="Add players to score (up to 15)"
          players={squad}
          onChange={setSquad}
          placeholder="Search & add players…"
          maxPlayers={15}
        />
        <button
          type="submit"
          disabled={loading || squad.filter(Boolean).length < 2}
          className="btn-primary w-full"
        >
          {loading
            ? <><span className="animate-spin mr-2">⏳</span>Scoring squad…</>
            : '🏆 Score & Rank Fantasy XI'}
        </button>
      </form>

      {error && <div className="glass p-4 text-sm text-red-400 border border-red-500/20 rounded-xl">{error}</div>}

      <AnimatePresence>
        {players && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-5">

            {/* Tab bar */}
            <div className="flex gap-2 p-1 rounded-xl w-fit" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <button onClick={() => setTab('xi')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'xi' ? 'bg-amber-500 text-white' : 'text-slate-400'}`}>
                🏆 Ranked XI
              </button>
              <button onClick={() => setTab('ai')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'ai' ? 'bg-indigo-500 text-white' : 'text-slate-400'}`}>
                💬 AI Picks {loading ? '⏳' : ''}
              </button>
            </div>

            {/* Captain / VC strip */}
            {tab === 'xi' && captain && (
              <div className="flex gap-3 flex-wrap">
                <div className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold"
                  style={{ background: 'rgba(245,200,66,0.12)', border: '1px solid rgba(245,200,66,0.25)', color: '#f5c842' }}>
                  👑 Captain: {captain}
                  <button
                    onClick={() => {
                      const next = players.find(p => p.name !== captain && p.name !== viceCaptain)
                      if (next) setCaptain(next.name)
                    }}
                    className="text-[10px] text-slate-500 hover:text-white ml-1"
                  >↺</button>
                </div>
                {viceCaptain && (
                  <div className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold"
                    style={{ background: 'rgba(129,140,248,0.12)', border: '1px solid rgba(129,140,248,0.25)', color: '#818cf8' }}>
                    🥈 Vice-Captain: {viceCaptain}
                    <button
                      onClick={() => {
                        const next = players.find(p => p.name !== captain && p.name !== viceCaptain)
                        if (next) setViceCaptain(next.name)
                      }}
                      className="text-[10px] text-slate-500 hover:text-white ml-1"
                    >↺</button>
                  </div>
                )}
              </div>
            )}

            {/* Ranked list */}
            {tab === 'xi' && (
              <div className="space-y-2">
                {players.map((p, i) => {
                  const isCap = p.name === captain
                  const isVC  = p.name === viceCaptain
                  const effectivePts = isCap ? p.score * 2 : isVC ? p.score * 1.5 : p.score
                  return (
                    <motion.div
                      key={p.name}
                      initial={{ opacity: 0, x: -16 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.04 }}
                      className="flex items-center gap-3 px-4 py-3 rounded-xl cursor-pointer"
                      style={{ background: isCap ? 'rgba(245,200,66,0.07)' : isVC ? 'rgba(129,140,248,0.07)' : 'rgba(255,255,255,0.02)', border: `1px solid ${isCap ? 'rgba(245,200,66,0.2)' : isVC ? 'rgba(129,140,248,0.2)' : 'rgba(255,255,255,0.06)'}` }}
                      onClick={() => {
                        if (!isCap && !isVC) setCaptain(p.name)
                        else if (isCap) { setCaptain(null) }
                        else setViceCaptain(null)
                      }}
                    >
                      {/* Rank */}
                      <span className="text-base w-6 text-center flex-shrink-0">{medal(i)}</span>

                      {/* Initials */}
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
                        style={{ background: isCap ? 'rgba(245,200,66,0.3)' : isVC ? 'rgba(129,140,248,0.3)' : 'rgba(255,107,53,0.2)' }}
                      >
                        {p.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
                      </div>

                      {/* Name + role */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-slate-100 truncate">{p.name}</p>
                          {isCap && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-amber-400/20 text-amber-300">C</span>}
                          {isVC  && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-indigo-400/20 text-indigo-300">VC</span>}
                        </div>
                        <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full border ${ROLE_COLOR[p.role]}`}>
                          {ROLE_LABEL[p.role]}
                        </span>
                      </div>

                      {/* Score */}
                      <div className="text-right flex-shrink-0">
                        <p className="text-lg font-bold" style={{ color: isCap ? '#f5c842' : '#ff6b35' }}>
                          {effectivePts.toFixed(1)}
                        </p>
                        <p className="text-[9px] text-slate-600 uppercase">pts{isCap ? ' ×2' : isVC ? ' ×1.5' : ''}</p>
                      </div>

                      {/* Mini bat/bowl bars */}
                      {p.stats && (
                        <div className="hidden sm:flex flex-col gap-0.5 w-16 flex-shrink-0">
                          {p.stats.batter && (
                            <div className="flex items-center gap-1">
                              <span className="text-[8px] text-slate-600 w-3">🏏</span>
                              <div className="flex-1 h-1.5 rounded-full bg-white/5">
                                <div className="h-full rounded-full bg-orange-400" style={{ width: `${Math.min((p.stats.batter.average / 60) * 100, 100)}%` }} />
                              </div>
                            </div>
                          )}
                          {p.stats.bowler && (
                            <div className="flex items-center gap-1">
                              <span className="text-[8px] text-slate-600 w-3">🎳</span>
                              <div className="flex-1 h-1.5 rounded-full bg-white/5">
                                <div className="h-full rounded-full bg-amber-400" style={{ width: `${Math.min((p.stats.bowler.total_wickets / 300) * 100, 100)}%` }} />
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </motion.div>
                  )
                })}

                <p className="text-[10px] text-slate-600 text-center pt-2">
                  Click a player to toggle Captain / tap again to clear. Points are based on career averages — not match-day projections.
                </p>
              </div>
            )}

            {/* AI tab */}
            {tab === 'ai' && (
              <div className="glass p-6">
                {loading && (
                  <div className="space-y-3">
                    <div className="shimmer-line h-4 w-3/4" />
                    <div className="shimmer-line h-4 w-full" />
                    <div className="shimmer-line h-4 w-5/6" />
                    <div className="shimmer-line h-4 w-2/3 mt-4" />
                  </div>
                )}
                {!loading && aiAnswer && (
                  <div className="prose prose-invert prose-sm max-w-none text-slate-300">
                    <ReactMarkdown>{aiAnswer}</ReactMarkdown>
                  </div>
                )}
                {!loading && !aiAnswer && <p className="text-sm text-slate-500">AI picks unavailable.</p>}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
