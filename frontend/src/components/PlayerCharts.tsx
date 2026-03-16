import { useState } from 'react'
import {
  BarChart, Bar, LineChart, Line, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { PlayerStats } from '../lib/api'

// ── Colour palette ────────────────────────────────────────────────────────────
const ORANGE     = '#ff6b35'
const GOLD       = '#f5c842'
const INDIGO     = '#818cf8'
const GREEN      = '#34d399'
const BAR_COLORS = [ORANGE, GOLD, INDIGO, GREEN, '#f87171', '#a78bfa', '#38bdf8']

// ── Shared tooltip style ──────────────────────────────────────────────────────
const TT = {
  contentStyle: {
    background: '#0f1629',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 8,
    fontSize: 12,
  },
  labelStyle: { color: '#94a3b8' },
  itemStyle:  { color: '#f1f5f9' },
}

// ── Avatar — deterministic colour gradient from player name ───────────────────
function PlayerAvatar({ name }: { name: string }) {
  const initials = name
    .split(' ')
    .filter(Boolean)
    .map(w => w[0].toUpperCase())
    .slice(0, 2)
    .join('')
  const hue  = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 360
  const hue2 = (hue + 45) % 360
  return (
    <div
      className="w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold text-white flex-shrink-0 select-none shadow-lg"
      style={{
        background: `linear-gradient(135deg, hsl(${hue},78%,52%), hsl(${hue2},88%,42%))`,
        border: '2px solid rgba(255,255,255,0.18)',
        textShadow: '0 1px 4px rgba(0,0,0,0.5)',
      }}
    >
      {initials}
    </div>
  )
}

// ── Stat pill ─────────────────────────────────────────────────────────────────
function StatPill({ label, value, accent = ORANGE }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="flex flex-col items-center p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
      <span className="text-xl font-bold" style={{ color: accent }}>{value}</span>
      <span className="text-[10px] text-slate-500 mt-0.5 uppercase tracking-wider">{label}</span>
    </div>
  )
}

// ── Chart section wrapper ─────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-bold uppercase tracking-widest text-slate-500 px-1">{title}</h4>
      <div className="rounded-xl p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
        {children}
      </div>
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function PlayerCharts({ stats }: { stats: PlayerStats }) {
  const { player, batter, bowler } = stats
  const [tab, setTab] = useState<'bat' | 'bowl'>(batter ? 'bat' : 'bowl')

  return (
    <div className="space-y-5 animate-fade-in">

      {/* Player header */}
      <div className="flex items-center gap-5 p-4 rounded-2xl" style={{ background: 'rgba(255,107,53,0.05)', border: '1px solid rgba(255,107,53,0.15)' }}>
        <PlayerAvatar name={player} />
        <div className="flex-1 min-w-0">
          <h3 className="text-xl font-bold text-white truncate" style={{ fontFamily: '"Playfair Display", Georgia, serif' }}>
            {player}
          </h3>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            {batter && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold" style={{ background: 'rgba(255,107,53,0.15)', color: ORANGE }}>
                🏏 Batter
              </span>
            )}
            {bowler && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold" style={{ background: 'rgba(245,200,66,0.15)', color: GOLD }}>
                🎳 Bowler
              </span>
            )}
            {!batter && !bowler && (
              <span className="text-xs text-slate-500">No Cricsheet data found for this player</span>
            )}
          </div>
        </div>
      </div>

      {/* Tab switcher */}
      {batter && bowler && (
        <div className="flex gap-2 p-1 rounded-xl w-fit" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
          <button
            onClick={() => setTab('bat')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'bat' ? 'bg-orange-500 text-white' : 'text-slate-400'}`}
          >
            🏏 Batting
          </button>
          <button
            onClick={() => setTab('bowl')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'bowl' ? 'bg-amber-500 text-white' : 'text-slate-400'}`}
          >
            🎳 Bowling
          </button>
        </div>
      )}

      {/* ════════════════════════════════════════════ BATTING PANEL */}
      {batter && tab === 'bat' && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            <StatPill label="Runs"    value={batter.total_runs.toLocaleString()} accent={ORANGE} />
            <StatPill label="Matches" value={batter.total_matches}               accent={GOLD} />
            <StatPill label="Average" value={batter.average}                     accent={GREEN} />
            <StatPill label="S/R"     value={batter.strike_rate}                 accent={INDIGO} />
            <StatPill label="4s"      value={batter.fours}                       accent={GOLD} />
            <StatPill label="6s"      value={batter.sixes}                       accent={ORANGE} />
          </div>

          {batter.runs_per_match.length > 0 && (
            <Section title="Runs & Strike Rate — Last 20 Innings">
              <ResponsiveContainer width="100%" height={220}>
                <LineChart
                  data={batter.runs_per_match.map(d => ({
                    ...d,
                    sr: d.balls > 0 ? +((d.runs / d.balls) * 100).toFixed(1) : 0,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="match" tick={{ fill: '#64748b', fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis
                    yAxisId="r"
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    width={32}
                    label={{ value: 'Runs', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }}
                  />
                  <YAxis
                    yAxisId="sr"
                    orientation="right"
                    tick={{ fill: '#818cf8', fontSize: 11 }}
                    width={40}
                    label={{ value: 'S/R', angle: 90, position: 'insideRight', fill: '#818cf8', fontSize: 10 }}
                  />
                  <Tooltip
                    {...TT}
                    formatter={((v: unknown, name: unknown) => [name === 'S/R' ? `${v}` : v, name]) as never}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                  <Line yAxisId="r"  type="monotone" dataKey="runs" stroke={ORANGE} strokeWidth={2} dot={{ r: 3, fill: ORANGE }} activeDot={{ r: 5 }} name="Runs" />
                  <Line yAxisId="sr" type="monotone" dataKey="sr"   stroke={INDIGO} strokeWidth={2} dot={{ r: 3, fill: INDIGO }} activeDot={{ r: 5 }} name="S/R" />
                </LineChart>
              </ResponsiveContainer>
            </Section>
          )}

          {batter.format_runs.length > 0 && (
            <div className="grid md:grid-cols-2 gap-4">
              <Section title="Runs by Format">
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={batter.format_runs} layout="vertical" barSize={14}>
                    <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
                    <YAxis type="category" dataKey="format" tick={{ fill: '#94a3b8', fontSize: 12 }} width={42} />
                    <Tooltip {...TT} />
                    <Bar dataKey="runs" fill={GOLD} radius={[0, 4, 4, 0]} name="Runs" />
                  </BarChart>
                </ResponsiveContainer>
              </Section>

              {batter.dismissals.length > 0 && (
                <Section title="Dismissal Types">
                  <ResponsiveContainer width="100%" height={160}>
                    <BarChart data={batter.dismissals} layout="vertical" barSize={12}>
                      <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
                      <YAxis type="category" dataKey="type" tick={{ fill: '#94a3b8', fontSize: 10 }} width={80} />
                      <Tooltip {...TT} formatter={((v: unknown) => [v, 'Times']) as never} />
                      <Bar dataKey="count" radius={[0, 4, 4, 0]} name="Times">
                        {batter.dismissals.map((_, i) => (
                          <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </Section>
              )}
            </div>
          )}
        </div>
      )}

      {/* ════════════════════════════════════════════ BOWLING PANEL */}
      {bowler && tab === 'bowl' && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            <StatPill label="Wickets" value={bowler.total_wickets}                accent={GOLD} />
            <StatPill label="Matches" value={bowler.total_matches}                accent={ORANGE} />
            <StatPill label="Economy" value={bowler.economy}                      accent={GREEN} />
            <StatPill label="Average" value={bowler.average}                      accent={INDIGO} />
            <StatPill label="S/R"     value={bowler.strike_rate}                  accent={GOLD} />
            <StatPill label="Balls"   value={bowler.total_balls.toLocaleString()} accent={ORANGE} />
          </div>

          {bowler.wickets_per_match.length > 0 && (
            <Section title="Wickets & Economy — Last 20 Matches">
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={bowler.wickets_per_match}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="match" tick={{ fill: '#64748b', fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis
                    yAxisId="w"
                    tick={{ fill: '#f5c842', fontSize: 11 }}
                    width={24}
                    allowDecimals={false}
                    label={{ value: 'Wkts', angle: -90, position: 'insideLeft', fill: '#f5c842', fontSize: 10 }}
                  />
                  <YAxis
                    yAxisId="e"
                    orientation="right"
                    tick={{ fill: '#818cf8', fontSize: 11 }}
                    width={36}
                    label={{ value: 'Econ', angle: 90, position: 'insideRight', fill: '#818cf8', fontSize: 10 }}
                  />
                  <Tooltip {...TT} />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                  <Line yAxisId="w" type="monotone" dataKey="wickets" stroke={GOLD}   strokeWidth={2} dot={{ r: 3, fill: GOLD }}   activeDot={{ r: 5 }} name="Wickets" />
                  <Line yAxisId="e" type="monotone" dataKey="economy" stroke={INDIGO} strokeWidth={2} dot={{ r: 3, fill: INDIGO }} activeDot={{ r: 5 }} name="Economy" />
                </LineChart>
              </ResponsiveContainer>
            </Section>
          )}

          {bowler.format_wickets.length > 0 && (
            <Section title="Wickets by Format">
              <ResponsiveContainer width="100%" height={150}>
                <BarChart data={bowler.format_wickets} layout="vertical" barSize={14}>
                  <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
                  <YAxis type="category" dataKey="format" tick={{ fill: '#94a3b8', fontSize: 12 }} width={42} />
                  <Tooltip {...TT} />
                  <Bar dataKey="wickets" fill={ORANGE} radius={[0, 4, 4, 0]} name="Wickets" />
                </BarChart>
              </ResponsiveContainer>
            </Section>
          )}
        </div>
      )}
    </div>
  )
}
