import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import PlayerSearchInput from '../components/PlayerSearchInput'
import { callAsk, callPlayerStats, PlayerStats } from '../lib/api'
import ReactMarkdown from 'react-markdown'

interface Props { apiBase: string; format: string; grounded: boolean }

const ORANGE = '#ff6b35'
const INDIGO = '#818cf8'

// ── Stat comparison bar ──────────────────────────────────────────────────────
function CompareBar({
  label, valA, valB, higherIsBetter = true,
}: {
  label: string
  valA: number
  valB: number
  higherIsBetter?: boolean
}) {
  const maxVal = Math.max(valA, valB, 0.01)
  const pctA = (valA / maxVal) * 100
  const pctB = (valB / maxVal) * 100
  const betterA = higherIsBetter ? valA >= valB : valA <= valB
  const betterB = higherIsBetter ? valB >= valA : valB <= valA

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px]">
        <span className={`font-bold tabular-nums ${betterA ? 'text-orange-400' : 'text-slate-500'}`}>{valA.toLocaleString()}</span>
        <span className="text-slate-600 uppercase tracking-wider text-[9px]">{label}</span>
        <span className={`font-bold tabular-nums ${betterB ? 'text-indigo-400' : 'text-slate-500'}`}>{valB.toLocaleString()}</span>
      </div>
      <div className="flex gap-1 h-2">
        {/* Left bar (Player A — grows right) */}
        <div className="flex-1 flex justify-end rounded-l-full overflow-hidden bg-white/5">
          <div
            className="h-full rounded-l-full transition-all duration-700"
            style={{ width: `${pctA}%`, background: betterA ? ORANGE : 'rgba(255,107,53,0.25)' }}
          />
        </div>
        {/* Divider */}
        <div className="w-px bg-white/10 flex-shrink-0" />
        {/* Right bar (Player B — grows left) */}
        <div className="flex-1 rounded-r-full overflow-hidden bg-white/5">
          <div
            className="h-full rounded-r-full transition-all duration-700"
            style={{ width: `${pctB}%`, background: betterB ? INDIGO : 'rgba(129,140,248,0.25)' }}
          />
        </div>
      </div>
    </div>
  )
}

// ── Initials avatar ──────────────────────────────────────────────────────────
function Avatar({ name, color }: { name: string; color: string }) {
  const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
  return (
    <div
      className="w-14 h-14 rounded-full flex items-center justify-center text-lg font-bold text-white flex-shrink-0"
      style={{ background: `linear-gradient(135deg, ${color}, ${color}88)`, border: `2px solid ${color}44` }}
    >
      {initials}
    </div>
  )
}

// ── Single stat pill ─────────────────────────────────────────────────────────
function Pill({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="text-center p-2.5 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
      <p className="text-base font-bold" style={{ color }}>{value}</p>
      <p className="text-[9px] text-slate-600 uppercase tracking-wide mt-0.5">{label}</p>
    </div>
  )
}

export default function PlayerCompare({ apiBase, format, grounded }: Props) {
  const [nameA, setNameA] = useState('')
  const [nameB, setNameB] = useState('')
  const [statsA, setStatsA] = useState<PlayerStats | null>(null)
  const [statsB, setStatsB] = useState<PlayerStats | null>(null)
  const [aiAnswer, setAiAnswer] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'bat' | 'bowl' | 'ai'>('bat')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!nameA.trim() || !nameB.trim()) return
    setError(null); setStatsA(null); setStatsB(null); setAiAnswer(null)
    setLoading(true)

    const [resA, resB, aiRes] = await Promise.allSettled([
      callPlayerStats(apiBase, nameA.trim()),
      callPlayerStats(apiBase, nameB.trim()),
      callAsk(apiBase, {
        prompt: `Compare ${nameA} vs ${nameB} in ${format} cricket. Cover: batting averages, strike rates, centuries/fifties, bowling records if applicable, head-to-head era comparison, strengths and weaknesses, and who is the better fantasy pick right now. Be concise but analytical.`,
        context: { format, player_a: nameA, player_b: nameB },
        grounded,      }),
    ])

    if (resA.status === 'fulfilled') setStatsA(resA.value)
    else setError(`Failed to load ${nameA}: ${resA.reason}`)

    if (resB.status === 'fulfilled') setStatsB(resB.value)
    else setError(`Failed to load ${nameB}: ${resB.reason}`)

    if (aiRes.status === 'fulfilled') setAiAnswer(aiRes.value.answer)

    setLoading(false)
  }

  const batA = statsA?.batter
  const batB = statsB?.batter
  const bowlA = statsA?.bowler
  const bowlB = statsB?.bowler
  const hasBat = batA || batB
  const hasBowl = bowlA || bowlB
  const hasAny = statsA || statsB

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl flex-shrink-0 animate-float"
          style={{ background: 'linear-gradient(135deg,rgba(255,107,53,.2),rgba(129,140,248,.12))', border: '1px solid rgba(255,107,53,.25)' }}
        >
          ⚖️
        </div>
        <div className="pt-1">
          <h2 className="text-2xl font-bold text-white leading-tight" style={{ fontFamily: '"Playfair Display",Georgia,serif' }}>
            Player Comparison
          </h2>
          <p className="text-sm text-slate-500 mt-1">Side-by-side Cricsheet stats + AI analysis</p>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="glass-strong p-6 space-y-4">
        <div className="grid grid-cols-2 gap-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3 h-3 rounded-full" style={{ background: ORANGE }} />
              <label className="field-label mb-0">Player A</label>
            </div>
            <PlayerSearchInput
              apiBase={apiBase}
              value={nameA}
              onChange={setNameA}
              placeholder="e.g. V Kohli"
              label=""
              id="compare-a"
            />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3 h-3 rounded-full" style={{ background: INDIGO }} />
              <label className="field-label mb-0">Player B</label>
            </div>
            <PlayerSearchInput
              apiBase={apiBase}
              value={nameB}
              onChange={setNameB}
              placeholder="e.g. SR Tendulkar"
              label=""
              id="compare-b"
            />
          </div>
        </div>
        <button type="submit" disabled={loading || !nameA.trim() || !nameB.trim()} className="btn-primary w-full">
          {loading ? <><span className="animate-spin mr-2">⏳</span>Comparing…</> : '⚖️ Compare Players'}
        </button>
      </form>

      {error && <div className="glass p-4 text-sm text-red-400 border border-red-500/20 rounded-xl">{error}</div>}

      <AnimatePresence>
        {hasAny && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-5">

            {/* Player nameplates */}
            <div className="grid grid-cols-2 gap-4">
              {[
                { stats: statsA, name: nameA, color: ORANGE },
                { stats: statsB, name: nameB, color: INDIGO },
              ].map(({ stats, name, color }, idx) => (
                <div key={idx} className="glass p-4 flex items-center gap-3">
                  <Avatar name={stats?.player ?? name} color={color} />
                  <div className="min-w-0">
                    <p className="font-bold text-white truncate text-sm">{stats?.player ?? name}</p>
                    {stats?.found === false && <p className="text-[10px] text-red-400 mt-0.5">Not found in Cricsheet</p>}
                    <div className="flex gap-1 mt-1.5 flex-wrap">
                      {stats?.batter && <span className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold" style={{ background: `${color}22`, color }}>🏏 Bat</span>}
                      {stats?.bowler && <span className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold" style={{ background: `${color}22`, color }}>🎳 Bowl</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Tab bar */}
            <div className="flex gap-2 p-1 rounded-xl w-fit" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
              {hasBat  && <button onClick={() => setTab('bat')}  className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'bat'  ? 'bg-orange-500 text-white' : 'text-slate-400'}`}>🏏 Batting</button>}
              {hasBowl && <button onClick={() => setTab('bowl')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'bowl' ? 'bg-amber-500 text-white' : 'text-slate-400'}`}>🎳 Bowling</button>}
              <button onClick={() => setTab('ai')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'ai' ? 'bg-indigo-500 text-white' : 'text-slate-400'}`}>💬 AI Verdict</button>
            </div>

            {/* ── Batting comparison ── */}
            {tab === 'bat' && (
              <div className="glass p-6 space-y-6">
                {/* Quick pills row */}
                <div className="grid grid-cols-2 gap-4">
                  {[{ stats: statsA, color: ORANGE }, { stats: statsB, color: INDIGO }].map(({ stats, color }, idx) =>
                    stats?.batter ? (
                      <div key={idx} className="grid grid-cols-3 gap-2">
                        <Pill label="Runs"    value={stats.batter.total_runs.toLocaleString()} color={color} />
                        <Pill label="Avg"     value={stats.batter.average} color={color} />
                        <Pill label="S/R"     value={stats.batter.strike_rate} color={color} />
                        <Pill label="Matches" value={stats.batter.total_matches} color={color} />
                        <Pill label="4s"      value={stats.batter.fours} color={color} />
                        <Pill label="6s"      value={stats.batter.sixes} color={color} />
                      </div>
                    ) : (
                      <div key={idx} className="flex items-center justify-center text-slate-600 text-xs">No batting data</div>
                    )
                  )}
                </div>

                {/* Comparison bars */}
                {batA && batB && (
                  <div className="space-y-4 pt-2 border-t border-white/5">
                    <div className="flex justify-between text-[10px] text-slate-600 uppercase tracking-widest mb-1">
                      <span style={{ color: ORANGE }}>{statsA?.player ?? nameA}</span>
                      <span style={{ color: INDIGO }}>{statsB?.player ?? nameB}</span>
                    </div>
                    <CompareBar label="Total Runs"    valA={batA.total_runs}    valB={batB.total_runs} />
                    <CompareBar label="Average"       valA={batA.average}       valB={batB.average} />
                    <CompareBar label="Strike Rate"   valA={batA.strike_rate}   valB={batB.strike_rate} />
                    <CompareBar label="Matches"       valA={batA.total_matches} valB={batB.total_matches} />
                    <CompareBar label="Fours"         valA={batA.fours}         valB={batB.fours} />
                    <CompareBar label="Sixes"         valA={batA.sixes}         valB={batB.sixes} />
                  </div>
                )}

                {!batA && !batB && (
                  <p className="text-sm text-slate-500 text-center">No batting data available for either player.</p>
                )}
              </div>
            )}

            {/* ── Bowling comparison ── */}
            {tab === 'bowl' && (
              <div className="glass p-6 space-y-6">
                <div className="grid grid-cols-2 gap-4">
                  {[{ stats: statsA, color: ORANGE }, { stats: statsB, color: INDIGO }].map(({ stats, color }, idx) =>
                    stats?.bowler ? (
                      <div key={idx} className="grid grid-cols-3 gap-2">
                        <Pill label="Wickets" value={stats.bowler.total_wickets} color={color} />
                        <Pill label="Economy" value={stats.bowler.economy} color={color} />
                        <Pill label="Avg"     value={stats.bowler.average} color={color} />
                        <Pill label="Matches" value={stats.bowler.total_matches} color={color} />
                        <Pill label="S/R"     value={stats.bowler.strike_rate} color={color} />
                        <Pill label="Balls"   value={stats.bowler.total_balls.toLocaleString()} color={color} />
                      </div>
                    ) : (
                      <div key={idx} className="flex items-center justify-center text-slate-600 text-xs">No bowling data</div>
                    )
                  )}
                </div>

                {bowlA && bowlB && (
                  <div className="space-y-4 pt-2 border-t border-white/5">
                    <div className="flex justify-between text-[10px] text-slate-600 uppercase tracking-widest mb-1">
                      <span style={{ color: ORANGE }}>{statsA?.player ?? nameA}</span>
                      <span style={{ color: INDIGO }}>{statsB?.player ?? nameB}</span>
                    </div>
                    <CompareBar label="Wickets"   valA={bowlA.total_wickets} valB={bowlB.total_wickets} />
                    <CompareBar label="Economy"   valA={bowlA.economy}       valB={bowlB.economy}       higherIsBetter={false} />
                    <CompareBar label="Average"   valA={bowlA.average}       valB={bowlB.average}       higherIsBetter={false} />
                    <CompareBar label="Strike Rt" valA={bowlA.strike_rate}   valB={bowlB.strike_rate}   higherIsBetter={false} />
                    <CompareBar label="Matches"   valA={bowlA.total_matches} valB={bowlB.total_matches} />
                  </div>
                )}

                {!bowlA && !bowlB && (
                  <p className="text-sm text-slate-500 text-center">No bowling data available for either player.</p>
                )}
              </div>
            )}

            {/* ── AI Verdict tab ── */}
            {tab === 'ai' && (
              <div className="glass p-6">
                {loading && (
                  <div className="space-y-3">
                    <div className="shimmer-line h-4 w-3/4" />
                    <div className="shimmer-line h-4 w-full" />
                    <div className="shimmer-line h-4 w-5/6" />
                  </div>
                )}
                {!loading && aiAnswer && (
                  <div className="prose prose-invert prose-sm max-w-none text-slate-300">
                    <ReactMarkdown>{aiAnswer}</ReactMarkdown>
                  </div>
                )}
                {!loading && !aiAnswer && (
                  <p className="text-sm text-slate-500">AI comparison unavailable.</p>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
