import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import { callAsk } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function BowlerStats({ apiBase, format, grounded }: Props) {
  const [player, setPlayer] = useState('')

  return (
    <ToolShell
      icon="🎳"
      title="Bowler Statistics"
      subtitle="Wickets, economy, average, recent form & fantasy value"
      onSubmit={() => callAsk(apiBase, {
        prompt: `Comprehensive bowling stats and analysis for ${player} in ${format} cricket. Include total wickets, economy rate, bowling average, strike rate, best figures, recent form (last 10 matches), pitch preferences, and fantasy value.`,
        context: { format, player },
        grounded,
      })}
    >
      <label className="field-label">Player Name</label>
      <input
        className="input"
        placeholder="e.g. Jasprit Bumrah"
        value={player}
        onChange={e => setPlayer(e.target.value)}
        required
      />
    </ToolShell>
  )
}
