import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import { callAsk } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function RecentMatches({ apiBase, format, grounded }: Props) {
  const [team, setTeam] = useState('')
  const [n, setN]       = useState(5)

  return (
    <ToolShell
      icon="📅"
      title="Recent Matches"
      subtitle="Results, scores, key performers & current form"
      onSubmit={() => callAsk(apiBase, {
        prompt: `List and analyse the last ${n} ${format} matches for ${team}. For each match include: date, opposition, venue, result, key scores, and standout performers. End with a current form summary and trend.`,
        context: { format, team, n },
        grounded,
      })}
    >
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2">
          <label className="field-label">Team Name</label>
          <input
            className="input"
            placeholder="e.g. Mumbai Indians"
            value={team}
            onChange={e => setTeam(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="field-label">No. of Matches</label>
          <input
            type="number"
            min={1} max={20}
            className="input"
            value={n}
            onChange={e => setN(Number(e.target.value))}
          />
        </div>
      </div>
    </ToolShell>
  )
}
