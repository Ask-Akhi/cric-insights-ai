import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import PlayerCharts from '../components/PlayerCharts'
import PlayerSearchInput from '../components/PlayerSearchInput'
import { callAsk, callPlayerStats, PlayerStats } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function BowlerStats({ apiBase, format, grounded }: Props) {
  const [player, setPlayer] = useState('')
  const [chartData, setChartData] = useState<PlayerStats | null>(null)
  const [chartLoading, setChartLoading] = useState(false)

  const handleSubmit = async () => {
    setChartData(null)
    setChartLoading(true)
    callPlayerStats(apiBase, player, format)
      .then(setChartData)
      .catch(() => setChartData(null))
      .finally(() => setChartLoading(false))

    return callAsk(apiBase, {
      prompt: `Comprehensive bowling stats and analysis for ${player} in ${format} cricket. Include total wickets, economy rate, bowling average, strike rate, best figures, recent form (last 10 matches), pitch preferences, and fantasy value.`,
      context: { format, player },
      grounded,
    })
  }

  return (
    <div className="space-y-6">
      <ToolShell
        icon="🎳"
        title="Bowler Statistics"
        subtitle="Wickets, economy, average, recent form & fantasy value"
        onSubmit={handleSubmit}
      >
        <PlayerSearchInput
          apiBase={apiBase}
          value={player}
          onChange={setPlayer}
          placeholder="e.g. JJ Bumrah"
          label="Player Name"
          id="bowler-search"
        />
      </ToolShell>

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
