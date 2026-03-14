import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import { callAsk } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function VenueStats({ apiBase, format, grounded }: Props) {
  const [venue, setVenue] = useState('')

  return (
    <ToolShell
      icon="🏟️"
      title="Venue Statistics"
      subtitle="Pitch conditions, average scores, batting/bowling nature & records"
      onSubmit={() => callAsk(apiBase, {
        prompt: `Detailed venue analysis for ${venue} in ${format} cricket. Include: average first innings score, average second innings score, pitch nature (batting/bowling/balanced), typical conditions, highest team scores, records at this ground, and advice for teams batting first vs second.`,
        context: { format, venue },
        grounded,
      })}
    >
      <label className="field-label">Venue / Stadium Name</label>
      <input
        className="input"
        placeholder="e.g. Wankhede Stadium, Mumbai"
        value={venue}
        onChange={e => setVenue(e.target.value)}
        required
      />
    </ToolShell>
  )
}
