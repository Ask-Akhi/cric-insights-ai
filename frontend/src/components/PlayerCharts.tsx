import { useState, useEffect } from 'react'
import {
  BarChart, Bar, LineChart, Line, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { PlayerStats } from '../lib/api'

// ── Cricsheet name → Wikipedia article title (for photo lookup) ───────────────
const WIKI_NAME: Record<string, string> = {
  'RG Sharma':          'Rohit Sharma',
  'V Kohli':            'Virat Kohli',
  'MS Dhoni':           'MS Dhoni',
  'JJ Bumrah':          'Jasprit Bumrah',
  'S Gill':             'Shubman Gill',
  'HH Pandya':          'Hardik Pandya',
  'KL Rahul':           'KL Rahul',
  'RA Jadeja':          'Ravindra Jadeja',
  'R Ashwin':           'Ravichandran Ashwin',
  'SA Yadav':           'Suryakumar Yadav',
  'RR Pant':            'Rishabh Pant',
  'SS Iyer':            'Shreyas Iyer',
  'Ishan Kishan':       'Ishan Kishan',
  'AR Patel':           'Axar Patel',
  'DL Chahar':          'Deepak Chahar',
  'Kuldeep Yadav':      'Kuldeep Yadav',
  'YS Chahal':          'Yuzvendra Chahal',
  'Yuvraj Singh':       'Yuvraj Singh',
  'SR Tendulkar':       'Sachin Tendulkar',
  'SC Ganguly':         'Sourav Ganguly',
  'R Dravid':           'Rahul Dravid',
  'Mohammed Shami':     'Mohammed Shami',
  'SPD Smith':          'Steve Smith (cricketer)',
  'DA Warner':          'David Warner (cricketer)',
  'PJ Cummins':         'Pat Cummins',
  'MA Starc':           'Mitchell Starc',
  'JR Hazlewood':       'Josh Hazlewood',
  'GJ Maxwell':         'Glenn Maxwell',
  'TM Head':            'Travis Head',
  'M Labuschagne':      'Marnus Labuschagne',
  'A Zampa':            'Adam Zampa',
  'JE Root':            'Joe Root',
  'BA Stokes':          'Ben Stokes',
  'JC Buttler':         'Jos Buttler',
  'JC Archer':          'Jofra Archer',
  'MA Wood':            'Mark Wood (cricketer)',
  'JM Bairstow':        'Jonny Bairstow',
  'HC Brook':           'Harry Brook',
  'JM Anderson':        'James Anderson (cricketer)',
  'SCJ Broad':          'Stuart Broad',
  'KS Williamson':      'Kane Williamson',
  'LRPL Taylor':        'Ross Taylor',
  'TA Boult':           'Trent Boult',
  'TG Southee':         'Tim Southee',
  'Babar Azam':         'Babar Azam',
  'Shaheen Shah Afridi':'Shaheen Shah Afridi',
  'Mohammad Rizwan':    'Mohammad Rizwan',
  'Shadab Khan':        'Shadab Khan',
  'AB de Villiers':     'AB de Villiers',
  'Q de Kock':          'Quinton de Kock',
  'K Rabada':           'Kagiso Rabada',
  'DW Steyn':           'Dale Steyn',
  'F du Plessis':       'Faf du Plessis',
  'AK Markram':         'Aiden Markram',
  'CH Gayle':           'Chris Gayle',
  'KA Pollard':         'Kieron Pollard',
  'AD Russell':         'Andre Russell',
  'N Pooran':           'Nicholas Pooran',
  'KC Sangakkara':      'Kumar Sangakkara',
  'DPMD Jayawardene':   'Mahela Jayawardene',
  'SL Malinga':         'Lasith Malinga',
  'AD Mathews':         'Angelo Mathews',
  'AS Hasaranga':       'Wanindu Hasaranga',
  'Rashid Khan':        'Rashid Khan (cricketer)',
  'Mohammad Nabi':      'Mohammad Nabi',
  'Shakib Al Hasan':    'Shakib Al Hasan',
  'Mushfiqur Rahim':    'Mushfiqur Rahim',
  'Tamim Iqbal':        'Tamim Iqbal',
}

function wikiTitle(cricsheetName: string): string {
  return WIKI_NAME[cricsheetName] ?? cricsheetName
}

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

// ── Avatar — tries Wikipedia photo, falls back to gradient initials ───────────
function PlayerAvatar({ name }: { name: string }) {
  const [imgSrc, setImgSrc] = useState<string | null>(null)
  const [imgErr, setImgErr] = useState(false)
  useEffect(() => {
    setImgSrc(null)
    setImgErr(false)
    const title = wikiTitle(name)
    const photoUrl = `https://en.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(title)}&prop=pageimages&format=json&pithumbsize=200&origin=*`
    fetch(photoUrl)
      .then(r => r.json())
      .then(data => {
        const pages = data?.query?.pages ?? {}
        const page = Object.values(pages)[0] as { thumbnail?: { source: string } }
        if (page?.thumbnail?.source) setImgSrc(page.thumbnail.source)
        else setImgErr(true)
      })
      .catch(() => setImgErr(true))
  }, [name])
  const initials = name
    .split(' ')
    .filter(Boolean)
    .map(w => w[0].toUpperCase())
    .slice(0, 2)
    .join('')
  const hue  = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 360
  const hue2 = (hue + 45) % 360

  const avatarClass = "w-24 h-24 rounded-full flex-shrink-0 shadow-xl"
  const ringStyle = { border: '3px solid rgba(255,107,53,0.5)', boxShadow: '0 0 20px rgba(255,107,53,0.2)' }

  // Still fetching — shimmer placeholder
  if (!imgSrc && !imgErr) {
    return (
      <div className={`${avatarClass} animate-pulse`}
        style={{ background: 'rgba(255,255,255,0.06)', ...ringStyle }} />
    )
  }

  return imgSrc && !imgErr ? (
    <img
      src={imgSrc}
      alt={wikiTitle(name)}
      onError={() => setImgErr(true)}
      className={`${avatarClass} object-cover object-top`}
      style={ringStyle}
    />
  ) : (
    <div
      className={`${avatarClass} flex items-center justify-center text-3xl font-bold text-white select-none`}
      style={{
        background: `linear-gradient(135deg, hsl(${hue},78%,52%), hsl(${hue2},88%,42%))`,
        ...ringStyle,
        textShadow: '0 2px 8px rgba(0,0,0,0.5)',
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
    <div className="space-y-5 animate-fade-in">      {/* Player header */}
      <div className="flex items-center gap-5 p-5 rounded-2xl" style={{ background: 'linear-gradient(135deg, rgba(255,107,53,0.08), rgba(245,200,66,0.04))', border: '1px solid rgba(255,107,53,0.2)' }}>
        <PlayerAvatar name={player} />
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-widest text-orange-500 mb-1">Player Profile</p>
          <h3 className="text-2xl font-bold text-white leading-tight truncate" style={{ fontFamily: '"Playfair Display", Georgia, serif' }}>
            {wikiTitle(player)}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">{player}</p>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            {batter && (
              <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold" style={{ background: 'rgba(255,107,53,0.15)', color: ORANGE, border: '1px solid rgba(255,107,53,0.2)' }}>
                🏏 Batter
              </span>
            )}
            {bowler && (
              <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold" style={{ background: 'rgba(245,200,66,0.15)', color: GOLD, border: '1px solid rgba(245,200,66,0.2)' }}>
                🎳 Bowler
              </span>
            )}
            {!batter && !bowler && (
              <span className="text-xs text-slate-500">No Cricsheet data found</span>
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
