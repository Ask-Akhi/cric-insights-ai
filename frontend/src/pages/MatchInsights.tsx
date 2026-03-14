import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import { callAsk } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function MatchInsights({ apiBase, format, grounded }: Props) {
  const [teamA,     setTeamA]     = useState('')
  const [teamB,     setTeamB]     = useState('')
  const [venue,     setVenue]     = useState('')
  const [matchDate, setMatchDate] = useState('')
  const [squadA,    setSquadA]    = useState('')
  const [squadB,    setSquadB]    = useState('')

  return (
    <ToolShell
      icon="🎯"
      title="Full Match Insights"
      subtitle="Complete pre-match AI report: playing XI, fantasy picks & match prediction"
      onSubmit={() => callAsk(apiBase, {
        prompt:
          `Analyse the upcoming ${format} match between ${teamA} and ${teamB} at ${venue}${matchDate ? ` on ${matchDate}` : ''}.\n` +
          `${squadA ? `${teamA} squad: ${squadA}\n` : ''}` +
          `${squadB ? `${teamB} squad: ${squadB}\n` : ''}` +
          `Provide a detailed report covering:\n` +
          `1. **Team Analysis** — current form, strengths & weaknesses\n` +
          `2. **Key Player Matchups** — batters vs bowlers to watch\n` +
          `3. **Pitch & Conditions** — venue stats, expected behaviour\n` +
          `4. **Predicted Playing XI** — for both teams with reasoning\n` +
          `5. **Top Fantasy Picks** — captain, vice-captain, differential picks\n` +
          `6. **Match Prediction** — winner with probability and reasoning`,
        context: { format, venue, team_a: teamA, team_b: teamB, squad_a: squadA, squad_b: squadB, date: matchDate },
        grounded,
      })}
    >
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="field-label">Team A</label>
          <input className="input" placeholder="e.g. Mumbai Indians" value={teamA} onChange={e => setTeamA(e.target.value)} required />
        </div>
        <div>
          <label className="field-label">Team B</label>
          <input className="input" placeholder="e.g. Chennai Super Kings" value={teamB} onChange={e => setTeamB(e.target.value)} required />
        </div>
        <div>
          <label className="field-label">Venue</label>
          <input className="input" placeholder="e.g. Wankhede Stadium" value={venue} onChange={e => setVenue(e.target.value)} required />
        </div>
        <div>
          <label className="field-label">Match Date (optional)</label>
          <input type="date" className="input" value={matchDate} onChange={e => setMatchDate(e.target.value)} />
        </div>
      </div>
      <div>
        <label className="field-label">Squad A — comma separated (optional)</label>
        <textarea className="input h-16 resize-none" placeholder="Rohit Sharma, Virat Kohli, Hardik Pandya..." value={squadA} onChange={e => setSquadA(e.target.value)} />
      </div>
      <div>
        <label className="field-label">Squad B — comma separated (optional)</label>
        <textarea className="input h-16 resize-none" placeholder="MS Dhoni, Ruturaj Gaikwad, Deepak Chahar..." value={squadB} onChange={e => setSquadB(e.target.value)} />
      </div>
    </ToolShell>
  )
}
