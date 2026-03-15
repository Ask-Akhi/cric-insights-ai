import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import PlayerCharts from '../components/PlayerCharts'
import PlayerSearchInput from '../components/PlayerSearchInput'
import { callAsk, callPlayerStats, PlayerStats } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function BatterStats({ apiBase, format, grounded }: Props) {
  const [player, setPlayer] = useState('')
  const [chartData, setChartData] = useState<PlayerStats | null>(null)
  const [chartLoading, setChartLoading] = useState(false)

  const handleSubmit = async () => {
    // Fetch charts in parallel with AI text
    setChartData(null)
    setChartLoading(true)
    callPlayerStats(apiBase, player)
      .then(setChartData)
      .catch(() => setChartData(null))
      .finally(() => setChartLoading(false))

    return callAsk(apiBase, {
      prompt: `Comprehensive batting stats and analysis for ${player} in ${format} cricket. Include career averages, strike rate, centuries, fifties, recent form (last 10 innings), strengths, weaknesses, and fantasy value.`,
      context: { format, player },
      grounded,
    })
  }

  return (
    <div className="space-y-6">
      <ToolShell
        icon="🏏"
        title="Batter Statistics"
        subtitle="Career averages, strike rate, recent form, strengths & fantasy value"
        onSubmit={handleSubmit}
      >
        <PlayerSearchInput
          apiBase={apiBase}
          value={player}
          onChange={setPlayer}
          placeholder="e.g. V Kohli"
          label="Player Name"
          id="batter-search"
        />
      </ToolShell>

      {/* Charts panel — shown below the AI result */}
      {chartLoading && (
        <div className="glass p-6 space-y-3 animate-fade-in">
          <p className="text-xs text-slate-500 uppercase tracking-widest font-semibold">Loading Cricsheet data…</p>
          <div className="shimmer-line h-4 w-1/2" />
          <div className="shimmer-line h-32 w-full" />
        </div>
      )}
      {!chartLoading && chartData?.found && (
        <div className="glass p-6">
          <div className="flex items-center gap-2 mb-5 pb-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
            <span className="text-[10px] font-bold tracking-widest uppercase text-amber-400">📊 Cricsheet Data Charts</span>
          </div>
          <PlayerCharts stats={chartData} />
        </div>
      )}
      {!chartLoading && chartData && !chartData.found && (
        <div className="glass p-4 text-xs text-slate-500 text-center">
          No Cricsheet match data found for <strong className="text-slate-300">{player}</strong> — charts unavailable.
        </div>
      )}
    </div>
  )
}
