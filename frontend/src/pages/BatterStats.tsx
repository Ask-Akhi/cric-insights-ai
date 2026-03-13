import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import { callAsk } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function BatterStats({ apiBase, format, grounded }: Props) {
  const [player, setPlayer] = useState('')

  return (
    <ToolShell
      icon="🏏"
      title="Batter Statistics"
      subtitle="Career averages, strike rate, recent form, strengths & fantasy value"
      onSubmit={() => callAsk(apiBase, {
        prompt: `Comprehensive batting stats and analysis for ${player} in ${format} cricket. Include career averages, strike rate, centuries, fifties, recent form (last 10 innings), strengths, weaknesses, and fantasy value.`,
        context: { format, player },
        grounded,
      })}
    >
      <label className="block text-xs text-slate-400 mb-1 font-medium">Player Name</label>
      <input
        className="input"
        placeholder="e.g. Virat Kohli"
        value={player}
        onChange={e => setPlayer(e.target.value)}
        required
      />
    </ToolShell>
  )
}
