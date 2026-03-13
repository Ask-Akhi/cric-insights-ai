import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import { callAsk } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function HeadToHead({ apiBase, format, grounded }: Props) {
  const [teamA, setTeamA] = useState('')
  const [teamB, setTeamB] = useState('')

  return (
    <ToolShell
      icon="⚔️"
      title="Head-to-Head Analysis"
      subtitle="Historical record, recent meetings, key player battles & prediction"
      onSubmit={() => callAsk(apiBase, {
        prompt: `Head-to-head analysis between ${teamA} and ${teamB} in ${format} cricket. Include: overall win-loss record, record in last 10 meetings, home/away breakdown, key player matchups, current form of both teams, and a match prediction with reasoning.`,
        context: { format, team_a: teamA, team_b: teamB },
        grounded,
      })}
    >
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-slate-400 mb-1 font-medium">Team A</label>
          <input
            className="input"
            placeholder="e.g. India"
            value={teamA}
            onChange={e => setTeamA(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1 font-medium">Team B</label>
          <input
            className="input"
            placeholder="e.g. Australia"
            value={teamB}
            onChange={e => setTeamB(e.target.value)}
            required
          />
        </div>
      </div>
    </ToolShell>
  )
}
