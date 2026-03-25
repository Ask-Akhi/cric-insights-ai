import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import PlayerCharts from '../components/PlayerCharts'
import PlayerSearchInput from '../components/PlayerSearchInput'
import { callAsk, callPlayerStats, PlayerStats } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean; onQuestionAsked?: () => void }

export default function BatterStats({ apiBase, format, grounded, onQuestionAsked }: Props) {
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
      prompt: `Comprehensive batting stats and analysis for ${player} in ${format} cricket. Include career averages, strike rate, centuries, fifties, recent form (last 10 innings), strengths, weaknesses, and fantasy value.`,
      context: { format, player },
      grounded,
    })
  }

  // Charts panel — passed as sidePanel prop
  const chartsPanel = (
    <>
      <div className="flex items-center gap-2 mb-4 pb-3" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <span className="text-[10px] font-bold tracking-widest uppercase text-amber-400">📊 Batting Stats</span>
        {chartLoading && (
          <span className="ml-auto text-[10px] text-slate-500 animate-pulse">Loading…</span>
        )}
      </div>
      {chartLoading && (
        <div className="space-y-3">
          <div className="shimmer-line h-20 w-full rounded-xl" />
          <div className="shimmer-line h-4 w-2/3" />
          <div className="shimmer-line h-32 w-full rounded-xl" />
        </div>
      )}
      {!chartLoading && chartData?.found && <PlayerCharts stats={chartData} />}
      {!chartLoading && chartData && !chartData.found && (
        <p className="text-xs text-slate-500 text-center py-6">
          No stats found for <strong className="text-slate-300">{player}</strong>
        </p>
      )}
    </>
  )
  return (
    <ToolShell
      icon="🏏"
      title="Batter Statistics"
      subtitle="Career averages, strike rate, recent form, strengths & fantasy value"
      onSubmit={handleSubmit}
      onQuestionAsked={onQuestionAsked}
      sidePanel={chartsPanel}
      sidePanelReady={chartLoading || !!chartData}
    >
      <PlayerSearchInput
        apiBase={apiBase}
        value={player}
        onChange={setPlayer}
        placeholder="e.g. Rohit Sharma or RG Sharma"
        label="Player Name"
        id="batter-search"
      />
    </ToolShell>
  )
}
