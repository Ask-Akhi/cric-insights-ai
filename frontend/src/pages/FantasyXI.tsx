import { useState, useCallback } from 'react'
import SquadBuilder from '../components/SquadBuilder'
import { callPlayerStats, callAsk } from '../lib/api'

// ── Types ─────────────────────────────────────────────────────────────────────
type Role = 'WK' | 'BAT' | 'AR' | 'BOWL' | '?'

interface PickedPlayer {
  name: string
  role: Role
  score: number
  runs: number
  wickets: number
  sr: number
  eco: number
  matches: number
  team: 'A' | 'B'
  isCap: boolean
  isVC: boolean
}

interface Props {
  apiBase: string
  format?: string
  grounded?: boolean
  onQuestionAsked?: () => void
}

// ── Role colours ──────────────────────────────────────────────────────────────
const ROLE_COLOR: Record<Role, string> = {
  WK:   '#f59e0b',
  BAT:  '#22d3ee',
  AR:   '#a78bfa',
  BOWL: '#4ade80',
  '?':  '#94a3b8',
}
const ROLE_BG: Record<Role, string> = {
  WK:   'rgba(245,158,11,0.15)',
  BAT:  'rgba(34,211,238,0.12)',
  AR:   'rgba(167,139,250,0.12)',
  BOWL: 'rgba(74,222,128,0.12)',
  '?':  'rgba(148,163,184,0.08)',
}

// ── Fantasy scoring (Dream11-style T20 approximation) ─────────────────────────
function calcFantasyScore(
  runs: number,
  wickets: number,
  sr: number,
  eco: number,
  matches: number,
  isCap: boolean,
  isVC: boolean,
): number {
  if (matches === 0) return 0
  const perMatch = { runs: runs / matches, wkts: wickets / matches }
  let pts = 0
  pts += perMatch.runs * 1
  pts += perMatch.wkts * 25
  if (sr > 170) pts += 6
  else if (sr > 150) pts += 4
  else if (sr > 130) pts += 2
  else if (sr > 0 && sr < 70) pts -= 6
  else if (sr > 0 && sr < 80) pts -= 4
  if (eco > 0 && eco < 6) pts += 6
  else if (eco > 0 && eco < 7) pts += 4
  else if (eco > 0 && eco < 8) pts += 2
  else if (eco > 10) pts -= 6
  else if (eco > 9) pts -= 4
  const multiplier = isCap ? 2 : isVC ? 1.5 : 1
  return Math.round(pts * multiplier * 10) / 10
}

// ── Role guesser ──────────────────────────────────────────────────────────────
function guessRole(
  batter: { total_runs: number; total_matches: number } | null,
  bowler: { total_wickets: number; total_matches: number } | null,
  forcedWK: boolean,
): Role {
  if (forcedWK) return 'WK'
  const batMatches = batter?.total_matches ?? 0
  const bowlMatches = bowler?.total_matches ?? 0
  const hasBat = batMatches > 2
  const hasBowl = bowlMatches > 2
  if (hasBat && hasBowl) return 'AR'
  if (hasBat) return 'BAT'
  if (hasBowl) return 'BOWL'
  return '?'
}

// ── Small components ──────────────────────────────────────────────────────────
function RoleBadge({ role }: { role: Role }) {
  return (
    <span
      className="text-[9px] font-bold px-1.5 py-0.5 rounded-full uppercase tracking-widest"
      style={{ color: ROLE_COLOR[role], background: ROLE_BG[role] }}
    >
      {role}
    </span>
  )
}

function CaptainBadge({ type }: { type: 'C' | 'VC' }) {
  return (
    <span
      className="text-[9px] font-black px-1.5 py-0.5 rounded-full"
      style={{
        background: type === 'C' ? 'rgba(245,158,11,0.9)' : 'rgba(167,139,250,0.9)',
        color: '#0f172a',
      }}
    >
      {type}
    </span>
  )
}

function PlayerCard({ p, onCycle }: { p: PickedPlayer; onCycle: (name: string) => void }) {
  return (
    <div
      className="relative flex flex-col items-center gap-1 p-2 rounded-xl cursor-pointer select-none transition-all"
      style={{ background: ROLE_BG[p.role], border: `1px solid ${ROLE_COLOR[p.role]}44`, minWidth: 72 }}
      onClick={() => onCycle(p.name)}
      title="Tap to cycle: Normal → Captain → Vice-Captain"
    >
      {(p.isCap || p.isVC) && (
        <div className="absolute -top-2 left-1/2 -translate-x-1/2">
          <CaptainBadge type={p.isCap ? 'C' : 'VC'} />
        </div>
      )}
      <div
        className="w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold"
        style={{ background: ROLE_BG[p.role], border: `2px solid ${ROLE_COLOR[p.role]}88` }}
      >
        {p.role === 'WK' ? '🧤' : p.role === 'BOWL' ? '⚾' : p.role === 'AR' ? '⚡' : '🏏'}
      </div>
      <span className="text-[10px] font-semibold text-white text-center leading-tight max-w-[72px] truncate" title={p.name}>
        {p.name.split(' ').pop()}
      </span>
      <RoleBadge role={p.role} />
      <span className="text-[11px] font-bold" style={{ color: ROLE_COLOR[p.role] }}>
        {p.score.toFixed(1)} pts
      </span>
      <div
        className="absolute top-1 right-1 w-2 h-2 rounded-full"
        style={{ background: p.team === 'A' ? '#3b82f6' : '#f43f5e' }}
        title={`Team ${p.team}`}
      />
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function FantasyXI({ apiBase, format, onQuestionAsked }: Props) {
  const [teamA, setTeamA] = useState('')
  const [teamB, setTeamB] = useState('')
  const [squadA, setSquadA] = useState<string[]>([])
  const [squadB, setSquadB] = useState<string[]>([])
  const [wkA, setWkA] = useState('')
  const [wkB, setWkB] = useState('')
  const [step, setStep] = useState<1 | 2>(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [picked, setPicked] = useState<PickedPlayer[]>([])
  const [activeTab, setActiveTab] = useState<'field' | 'list' | 'ai'>('field')
  const [aiAnswer, setAiAnswer] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [capName, setCapName] = useState('')
  const [vcName, setVcName] = useState('')

  const cycleCapVC = useCallback((name: string) => {
    if (capName !== name && vcName !== name) {
      setCapName(name)
    } else if (capName === name) {
      setVcName(name)
      setCapName('')
    } else {
      setVcName('')
    }
  }, [capName, vcName])

  const handleBuild = async () => {
    const allPlayers = [
      ...squadA.map(n => ({ name: n, team: 'A' as const })),
      ...squadB.map(n => ({ name: n, team: 'B' as const })),
    ]
    if (allPlayers.length < 2) { setError('Add at least 2 players across both squads.'); return }
    setLoading(true)
    setError('')
    try {
      const results = await Promise.allSettled(
        allPlayers.map(({ name, team }) =>
          callPlayerStats(apiBase, name, format).then(s => ({ s, team, name }))
        )
      )
      const players: PickedPlayer[] = results
        .filter(r => r.status === 'fulfilled')
        .map(r => {
          const { s, team, name } = (r as PromiseFulfilledResult<{
            s: Awaited<ReturnType<typeof callPlayerStats>>
            team: 'A' | 'B'
            name: string
          }>).value
          const forcedWK = (team === 'A' && wkA === name) || (team === 'B' && wkB === name)
          const role     = guessRole(s.batter, s.bowler, forcedWK)
          const runs     = s.batter?.total_runs ?? 0
          const wickets  = s.bowler?.total_wickets ?? 0
          const sr       = s.batter?.strike_rate ?? 0
          const eco      = s.bowler?.economy ?? 0
          const matches  = Math.max(s.batter?.total_matches ?? 0, s.bowler?.total_matches ?? 0)
          const score    = calcFantasyScore(runs, wickets, sr, eco, matches, false, false)
          return { name, role, score, runs, wickets, sr, eco, matches, team, isCap: false, isVC: false }
        })
      const sorted = [...players].sort((a, b) => b.score - a.score)
      const top11  = sorted.slice(0, 11)
      if (top11.length >= 1) setCapName(top11[0].name)
      if (top11.length >= 2) setVcName(top11[1].name)
      setPicked(top11)
      setStep(2)
      setActiveTab('field')
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const fetchAiPicks = async () => {
    if (aiAnswer) return
    setAiLoading(true)
    try {
      const names  = picked.map(p => p.name).join(', ')
      const prompt = `Given these cricket players: ${names}. Format: ${format ?? 'T20'}. Teams: ${teamA || 'Team A'} vs ${teamB || 'Team B'}. Pick the best Fantasy XI (11 players) with captain and vice-captain. Give brief reasons based on recent form and role balance.`
      const res    = await callAsk(apiBase, { prompt, use_graph: true })
      setAiAnswer(res.answer)
      onQuestionAsked?.()
    } catch (e) {
      setAiAnswer(`Could not fetch AI picks: ${String(e)}`)
    } finally {
      setAiLoading(false)
    }
  }

  const pickedWithFlags: PickedPlayer[] = picked.map(p => ({
    ...p,
    isCap:  p.name === capName,
    isVC:   p.name === vcName,
    score:  calcFantasyScore(p.runs, p.wickets, p.sr, p.eco, p.matches, p.name === capName, p.name === vcName),
  }))

  const byRole = (role: Role) => pickedWithFlags.filter(p => p.role === role)

  // ── Step 1: Squad input ───────────────────────────────────────────────────────
  if (step === 1) {
    return (
      <div className="space-y-6">
        <div className="text-center space-y-1">
          <h2 className="text-xl font-bold text-white">Fantasy XI Builder</h2>
          <p className="text-sm text-slate-400">Add both squads · pick your keeper · get ranked picks</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-4 items-start">
          {/* Team A */}
          <div className="rounded-2xl p-4 space-y-4"
            style={{ background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.2)' }}>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-blue-500" />
              <input
                className="input flex-1 text-sm"
                placeholder="Team A name (e.g. India)"
                value={teamA}
                onChange={e => setTeamA(e.target.value)}
              />
            </div>
            <SquadBuilder
              apiBase={apiBase} label="Squad A" players={squadA}
              onChange={setSquadA} placeholder="Add player…" maxPlayers={15}
            />
            {squadA.length > 0 && (
              <div className="space-y-1">
                <label className="field-label">Wicketkeeper (A)</label>
                <select className="input text-sm w-full" value={wkA} onChange={e => setWkA(e.target.value)}>
                  <option value="">— select keeper —</option>
                  {squadA.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
            )}
          </div>

          {/* VS */}
          <div className="flex items-center justify-center py-4 md:py-0 md:pt-12">
            <div className="w-12 h-12 rounded-full flex items-center justify-center font-black text-base"
              style={{ background: 'rgba(255,107,53,0.15)', color: '#ff6b35', border: '2px solid rgba(255,107,53,0.3)' }}>
              VS
            </div>
          </div>

          {/* Team B */}
          <div className="rounded-2xl p-4 space-y-4"
            style={{ background: 'rgba(244,63,94,0.06)', border: '1px solid rgba(244,63,94,0.2)' }}>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-rose-500" />
              <input
                className="input flex-1 text-sm"
                placeholder="Team B name (e.g. Australia)"
                value={teamB}
                onChange={e => setTeamB(e.target.value)}
              />
            </div>
            <SquadBuilder
              apiBase={apiBase} label="Squad B" players={squadB}
              onChange={setSquadB} placeholder="Add player…" maxPlayers={15}
            />
            {squadB.length > 0 && (
              <div className="space-y-1">
                <label className="field-label">Wicketkeeper (B)</label>
                <select className="input text-sm w-full" value={wkB} onChange={e => setWkB(e.target.value)}>
                  <option value="">— select keeper —</option>
                  {squadB.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
            )}
          </div>
        </div>

        {error && (
          <div className="rounded-xl px-4 py-3 text-sm text-red-400"
            style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
            {error}
          </div>
        )}

        <button
          className="btn-primary w-full py-3 text-base font-bold disabled:opacity-40"
          disabled={loading || (squadA.length + squadB.length) < 2}
          onClick={handleBuild}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
              Fetching stats…
            </span>
          ) : '⚡ Build Fantasy XI'}
        </button>
      </div>
    )
  }

  // ── Step 2: Results ───────────────────────────────────────────────────────────
  const totalScore = pickedWithFlags.reduce((s, p) => s + p.score, 0)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">
            {teamA || 'Team A'} <span className="text-slate-500 text-sm font-normal">vs</span> {teamB || 'Team B'}
          </h2>
          <p className="text-xs text-slate-400">{pickedWithFlags.length} players · {totalScore.toFixed(1)} total pts</p>
        </div>
        <button
          className="text-xs px-3 py-1.5 rounded-lg text-slate-400 hover:text-white transition-colors"
          style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
          onClick={() => { setStep(1); setPicked([]); setAiAnswer('') }}
        >
          ↺ Rebuild
        </button>
      </div>

      {/* C/VC hint */}
      <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
        <span>Tap a card to cycle:</span>
        <CaptainBadge type="C" /><span>Captain ×2</span>
        <CaptainBadge type="VC" /><span>Vice-Captain ×1.5</span>
        <span className="text-slate-600">· tap again to clear</span>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl" style={{ background: 'rgba(255,255,255,0.04)' }}>
        {(['field', 'list', 'ai'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => { setActiveTab(tab); if (tab === 'ai') fetchAiPicks() }}
            className="flex-1 py-2 rounded-lg text-xs font-semibold transition-all"
            style={{
              background: activeTab === tab ? 'rgba(255,107,53,0.2)' : 'transparent',
              color: activeTab === tab ? '#ff6b35' : '#64748b',
            }}
          >
            {tab === 'field' ? '🏟 Field View' : tab === 'list' ? '📋 List View' : '🤖 AI Picks'}
          </button>
        ))}
      </div>

      {/* ── Field View ── */}
      {activeTab === 'field' && (
        <div className="rounded-2xl p-4 space-y-5"
          style={{ background: 'linear-gradient(180deg,rgba(34,197,94,0.07) 0%,rgba(16,185,129,0.03) 100%)', border: '1px solid rgba(34,197,94,0.15)' }}>
          {(['BOWL', 'AR', 'BAT', 'WK'] as Role[]).map((role, idx, arr) => (
            <div key={role} className="space-y-2">
              <p className="text-center text-[10px] text-slate-600 uppercase tracking-widest">
                {role === 'BOWL' ? 'Bowlers' : role === 'AR' ? 'All-Rounders' : role === 'BAT' ? 'Batters' : 'Wicketkeeper'}
              </p>
              <div className="flex flex-wrap justify-center gap-3">
                {role === 'BAT'
                  ? byRole('BAT').concat(byRole('?')).map(p => <PlayerCard key={p.name} p={p} onCycle={cycleCapVC} />)
                  : byRole(role).map(p => <PlayerCard key={p.name} p={p} onCycle={cycleCapVC} />)
                }
                {(role === 'BAT'
                  ? byRole('BAT').length + byRole('?').length
                  : byRole(role).length) === 0 && (
                  <span className="text-[11px] text-slate-600 italic">
                    {role === 'WK' ? 'None — select a keeper in Step 1' : '—'}
                  </span>
                )}
              </div>
              {idx < arr.length - 1 && (
                <div className="w-full h-px" style={{ background: 'rgba(255,255,255,0.05)' }} />
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── List View ── */}
      {activeTab === 'list' && (
        <div className="space-y-2">
          {[...pickedWithFlags].sort((a, b) => b.score - a.score).map((p, i) => (
            <div
              key={p.name}
              className="flex items-center gap-3 px-4 py-3 rounded-xl cursor-pointer transition-all"
              style={{
                background: p.isCap ? 'rgba(245,158,11,0.08)' : p.isVC ? 'rgba(167,139,250,0.08)' : 'rgba(255,255,255,0.03)',
                border: p.isCap ? '1px solid rgba(245,158,11,0.25)' : p.isVC ? '1px solid rgba(167,139,250,0.25)' : '1px solid rgba(255,255,255,0.06)',
              }}
              onClick={() => cycleCapVC(p.name)}
            >
              <span className="text-xs font-bold text-slate-600 w-5 text-right shrink-0">{i + 1}</span>
              <div className="w-6 flex items-center justify-center shrink-0">
                {p.isCap ? <CaptainBadge type="C" /> : p.isVC ? <CaptainBadge type="VC" /> : (
                  <div className="w-2 h-2 rounded-full" style={{ background: p.team === 'A' ? '#3b82f6' : '#f43f5e' }} />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-white truncate">{p.name}</span>
                  <RoleBadge role={p.role} />
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5 space-x-2">
                  {p.runs > 0 && <span>🏏 {p.runs}r</span>}
                  {p.wickets > 0 && <span>⚾ {p.wickets}w</span>}
                  {p.sr > 0 && <span>SR {p.sr.toFixed(0)}</span>}
                  {p.eco > 0 && <span>Eco {p.eco.toFixed(2)}</span>}
                  {p.matches > 0 && <span>({p.matches} matches)</span>}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-base font-black" style={{ color: ROLE_COLOR[p.role] }}>{p.score.toFixed(1)}</div>
                <div className="text-[9px] text-slate-600">pts</div>
              </div>
            </div>
          ))}
          <div className="flex items-center gap-4 pt-2 px-1">
            <span className="flex items-center gap-1.5 text-xs text-slate-500">
              <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />{teamA || 'Team A'}
            </span>
            <span className="flex items-center gap-1.5 text-xs text-slate-500">
              <span className="w-2 h-2 rounded-full bg-rose-500 inline-block" />{teamB || 'Team B'}
            </span>
          </div>
        </div>
      )}

      {/* ── AI Picks ── */}
      {activeTab === 'ai' && (
        <div className="rounded-2xl p-5 space-y-3"
          style={{ background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.2)' }}>
          <div className="flex items-center gap-2">
            <span className="text-lg">��</span>
            <h3 className="text-sm font-bold text-purple-300">AI Fantasy Picks</h3>
          </div>
          {aiLoading ? (
            <div className="flex items-center gap-3 text-sm text-slate-400">
              <svg className="w-5 h-5 animate-spin text-purple-400" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
              Asking AI for picks…
            </div>
          ) : aiAnswer ? (
            <div className="prose prose-invert prose-sm max-w-none text-slate-300 leading-relaxed whitespace-pre-wrap text-sm">
              {aiAnswer}
            </div>
          ) : (
            <div className="text-sm text-slate-500">Loading AI analysis…</div>
          )}
          {!aiLoading && aiAnswer && (
            <button
              className="text-xs px-3 py-1.5 rounded-lg text-purple-400 hover:text-purple-300 transition-colors"
              style={{ background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.2)' }}
              onClick={() => { setAiAnswer(''); fetchAiPicks() }}
            >
              ↺ Regenerate
            </button>
          )}
        </div>
      )}

      {/* Footer score bar */}
      <div className="rounded-xl px-4 py-3 flex items-center justify-between text-xs"
        style={{ background: 'rgba(255,107,53,0.06)', border: '1px solid rgba(255,107,53,0.12)' }}>
        <span className="text-slate-400">
          {capName && <span>C: <strong className="text-amber-400">{capName.split(' ').pop()}</strong></span>}
          {vcName && <span className="ml-3">VC: <strong className="text-purple-400">{vcName.split(' ').pop()}</strong></span>}
          {!capName && !vcName && <span className="text-slate-600">Tap a player to assign C / VC</span>}
        </span>
        <span className="font-bold text-orange-400">{totalScore.toFixed(1)} pts total</span>
      </div>
    </div>
  )
}
