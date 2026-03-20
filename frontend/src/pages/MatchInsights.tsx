import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import MatchForm, { MatchFormData } from './MatchForm'
import { callAsk } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean; onQuestionAsked?: () => void }

export default function MatchInsights({ apiBase, format, grounded, onQuestionAsked }: Props) {
  const [form, setForm] = useState<MatchFormData>({
    format, teamA: '', teamB: '', venue: '', matchDate: '', squadA: [], squadB: [],
  })

  const handleSubmit = () => {
    const squadA = form.squadA.join(', ')
    const squadB = form.squadB.join(', ')
    return callAsk(apiBase, {
      prompt:
        `Analyse the upcoming ${form.format} match between ${form.teamA} and ${form.teamB} at ${form.venue}` +
        (form.matchDate ? ` on ${form.matchDate}` : '') + '.\n' +
        (squadA ? `${form.teamA} squad: ${squadA}\n` : '') +
        (squadB ? `${form.teamB} squad: ${squadB}\n` : '') +
        `Provide a detailed report covering:\n` +
        `1. **Team Analysis** — current form, strengths & weaknesses\n` +
        `2. **Key Player Matchups** — batters vs bowlers to watch\n` +
        `3. **Pitch & Conditions** — venue stats, expected behaviour\n` +
        `4. **Predicted Playing XI** — for both teams with reasoning\n` +
        `5. **Top Fantasy Picks** — captain, vice-captain, differential picks\n` +
        `6. **Match Prediction** — winner with probability and reasoning`,
      context: {
        format: form.format, venue: form.venue,
        team_a: form.teamA, team_b: form.teamB,
        squad_a: squadA, squad_b: squadB, date: form.matchDate,
      },
      grounded,
    })
  }
  return (
    <ToolShell
      icon="🎯"
      title="Full Match Insights"
      subtitle="Complete pre-match AI report: playing XI, fantasy picks & match prediction"
      onSubmit={handleSubmit}
      onQuestionAsked={onQuestionAsked}
    >
      <MatchForm apiBase={apiBase} value={form} onChange={setForm} />
    </ToolShell>
  )
}
