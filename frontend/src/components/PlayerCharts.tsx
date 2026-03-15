import { useState } from 'react'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { PlayerStats } from '../lib/api'

// ── Colour palette aligned with the app's theme ─────────────────────────────
const ORANGE  = '#ff6b35'
const GOLD    = '#f5c842'
const INDIGO  = '#818cf8'
const GREEN   = '#34d399'
const PIE_COLORS = [ORANGE, GOLD, INDIGO, GREEN, '#f87171', '#a78bfa', '#38bdf8']

// ── Shared tooltip style ─────────────────────────────────────────────────────
const TooltipStyle = {
  contentStyle: { background: '#0f1629', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 },
  labelStyle:   { color: '#94a3b8' },
  itemStyle:    { color: '#f1f5f9' },
}

// ── Player avatar using initials fallback ────────────────────────────────────
function PlayerAvatar({ name }: { name: string }) {
  const [imgFailed, setImgFailed] = useState(false)
  const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
  // Try ESPN Cricinfo / Cricbuzz style slug
  const slug = name.toLowerCase().replace(/\s+/g, '-')

  if (!imgFailed) {
    return (
      <img
        src={`https://img1.hscicdn.com/image/upload/f_auto,t_h_100_2x/lsci/db/PICTURES/CMS/315600/${slug}.jpg`}
        alt={name}
        onError={() => setImgFailed(true)}
        className="w-20 h-20 rounded-full object-cover border-2"
        style={{ borderColor: 'rgba(255,107,53,0.4)' }}
      />
    )
  }

  return (
    <div
      className="w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold text-white flex-shrink-0"
      style={{ background: 'linear-gradient(135deg, #ff6b35, #f5c842)', border: '2px solid rgba(255,107,53,0.4)' }}
    >
      {initials}
    </div>
  )
}

// ── Stat pill ────────────────────────────────────────────────────────────────
function StatPill({ label, value, accent = ORANGE }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="flex flex-col items-center p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
      <span className="text-xl font-bold" style={{ color: accent }}>{value}</span>
      <span className="text-[10px] text-slate-500 mt-0.5 uppercase tracking-wider">{label}</span>
    </div>
  )
}

// ── Section header ───────────────────────────────────────────────────────────
function ChartSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-bold uppercase tracking-widest text-slate-500 px-1">{title}</h4>
      <div className="rounded-xl p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
        {children}
      </div>
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────────────
interface Props {
  stats: PlayerStats
}

export default function PlayerCharts({ stats }: Props) {
  const { player, batter, bowler } = stats
  const [tab, setTab] = useState<'bat' | 'bowl'>(batter ? 'bat' : 'bowl')

  return (
    <div className="space-y-5 animate-fade-in">

      {/* Player header */}
      <div className="flex items-center gap-5 p-4 rounded-2xl" style={{ background: 'rgba(255,107,53,0.05)', border: '1px solid rgba(255,107,53,0.15)' }}>
        <PlayerAvatar name={player} />
        <div className="flex-1 min-w-0">
          <h3 className="text-xl font-bold text-white truncate" style={{ fontFamily: '"Playfair Display", Georgia, serif' }}>{player}</h3>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            {batter && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold" style={{ background: 'rgba(255,107,53,0.15)', color: ORANGE }}>🏏 Batter</span>
            )}
            {bowler && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold" style={{ background: 'rgba(245,200,66,0.15)', color: GOLD }}>🎳 Bowler</span>
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
          <button onClick={() => setTab('bat')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'bat' ? 'bg-orange-500 text-white' : 'text-slate-400'}`}>🏏 Batting</button>
          <button onClick={() => setTab('bowl')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'bowl' ? 'bg-amber-500 text-white' : 'text-slate-400'}`}>🎳 Bowling</button>
        </div>
      )}

      {/* ── Batting panel ──────────────────────────────────── */}
      {batter && tab === 'bat' && (
        <div className="space-y-4">
          {/* Summary pills */}
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            <StatPill label="Runs"     value={batter.total_runs.toLocaleString()} accent={ORANGE} />
            <StatPill label="Matches"  value={batter.total_matches} accent={GOLD} />
            <StatPill label="Average"  value={batter.average} accent={GREEN} />
            <StatPill label="S/R"      value={batter.strike_rate} accent={INDIGO} />
            <StatPill label="4s"       value={batter.fours} accent={GOLD} />
            <StatPill label="6s"       value={batter.sixes} accent={ORANGE} />
          </div>

          {/* Runs per match – bar chart */}
          {batter.runs_per_match.length > 0 && (
            <ChartSection title="Runs — Last 20 Innings">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={batter.runs_per_match} barSize={14}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="match" hide />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={28} />
                  <Tooltip {...TooltipStyle} formatter={(v: number, n: string) => [v, n === 'runs' ? 'Runs' : 'Balls']} />
                  <Bar dataKey="runs" fill={ORANGE} radius={[4, 4, 0, 0]} name="runs" />
                </BarChart>
              </ResponsiveContainer>
            </ChartSection>
          )}

          {/* Format comparison – bar chart */}
          {batter.format_runs.length > 0 && (
            <div className="grid md:grid-cols-2 gap-4">
              <ChartSection title="Runs by Format">
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={batter.format_runs} layout="vertical" barSize={14}>
                    <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
                    <YAxis type="category" dataKey="format" tick={{ fill: '#94a3b8', fontSize: 12 }} width={40} />
                    <Tooltip {...TooltipStyle} />
                    <Bar dataKey="runs" fill={GOLD} radius={[0, 4, 4, 0]} name="Runs" />
                  </BarChart>
                </ResponsiveContainer>
              </ChartSection>

              {/* Dismissal pie chart */}
              {batter.dismissals.length > 0 && (
                <ChartSection title="Dismissal Types">
                  <ResponsiveContainer width="100%" height={160}>
                    <PieChart>
                      <Pie data={batter.dismissals} dataKey="count" nameKey="type" cx="50%" cy="50%" outerRadius={60} label={({ type, percent }) => `${type} ${(percent * 100).toFixed(0)}%`} labelLine={false}
                        style={{ fontSize: 10, fill: '#94a3b8' }}>
                        {batter.dismissals.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <Tooltip {...TooltipStyle} />
                    </PieChart>
                  </ResponsiveContainer>
                </ChartSection>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Bowling panel ──────────────────────────────────── */}
      {bowler && tab === 'bowl' && (
        <div className="space-y-4">
          {/* Summary pills */}
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            <StatPill label="Wickets"  value={bowler.total_wickets} accent={GOLD} />
            <StatPill label="Matches"  value={bowler.total_matches} accent={ORANGE} />
            <StatPill label="Economy"  value={bowler.economy} accent={GREEN} />
            <StatPill label="Average"  value={bowler.average} accent={INDIGO} />
            <StatPill label="S/R"      value={bowler.strike_rate} accent={GOLD} />
            <StatPill label="Balls"    value={bowler.total_balls.toLocaleString()} accent={ORANGE} />
          </div>

          {/* Wickets per match – line chart */}
          {bowler.wickets_per_match.length > 0 && (
            <ChartSection title="Wickets — Last 20 Matches">
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={bowler.wickets_per_match}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="match" hide />
                  <YAxis yAxisId="l" tick={{ fill: '#64748b', fontSize: 11 }} width={20} />
                  <YAxis yAxisId="r" orientation="right" tick={{ fill: '#64748b', fontSize: 11 }} width={30} />
                  <Tooltip {...TooltipStyle} />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                  <Line yAxisId="l" type="monotone" dataKey="wickets" stroke={GOLD}   strokeWidth={2} dot={{ r: 3, fill: GOLD }}   name="Wickets" />
                  <Line yAxisId="r" type="monotone" dataKey="economy" stroke={INDIGO} strokeWidth={2} dot={{ r: 3, fill: INDIGO }} name="Economy" />
                </LineChart>
              </ResponsiveContainer>
            </ChartSection>
          )}

          {/* Wickets by format */}
          {bowler.format_wickets.length > 0 && (
            <ChartSection title="Wickets by Format">
              <ResponsiveContainer width="100%" height={150}>
                <BarChart data={bowler.format_wickets} layout="vertical" barSize={14}>
                  <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
                  <YAxis type="category" dataKey="format" tick={{ fill: '#94a3b8', fontSize: 12 }} width={40} />
                  <Tooltip {...TooltipStyle} />
                  <Bar dataKey="wickets" fill={ORANGE} radius={[0, 4, 4, 0]} name="Wickets" />
                </BarChart>
              </ResponsiveContainer>
            </ChartSection>
          )}
        </div>
      )}
    </div>
  )
}
