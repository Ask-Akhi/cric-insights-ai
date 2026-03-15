import React from 'react'
import SquadBuilder from '../components/SquadBuilder'

export interface MatchFormData {
  format: string
  teamA: string
  teamB: string
  venue: string
  matchDate: string
  squadA: string[]
  squadB: string[]
}

interface Props {
  apiBase: string
  value: MatchFormData
  onChange: (data: MatchFormData) => void
  formatLocked?: boolean
}

const FORMATS = ['T20', 'IT20', 'ODI', 'ODM', 'Test', 'IPL', 'BBL', 'CPL', 'PSL']

export default function MatchForm({ apiBase, value, onChange, formatLocked }: Props) {
  const set =
    (field: keyof Pick<MatchFormData, 'format' | 'teamA' | 'teamB' | 'venue' | 'matchDate'>) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      onChange({ ...value, [field]: e.target.value })

  return (
    <div className="space-y-4">
      {/* Format selector */}
      {!formatLocked && (
        <div>
          <label className="field-label">Format</label>
          <select className="input" value={value.format} onChange={set('format')}>
            {FORMATS.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
      )}

      {/* Teams */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="field-label">Team A</label>
          <input
            className="input"
            placeholder="e.g. Mumbai Indians"
            value={value.teamA}
            onChange={set('teamA')}
            required
          />
        </div>
        <div>
          <label className="field-label">Team B</label>
          <input
            className="input"
            placeholder="e.g. Chennai Super Kings"
            value={value.teamB}
            onChange={set('teamB')}
            required
          />
        </div>
      </div>

      {/* Venue + Date */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="field-label">Venue</label>
          <input
            className="input"
            placeholder="e.g. Wankhede Stadium"
            value={value.venue}
            onChange={set('venue')}
            required
          />
        </div>
        <div>
          <label className="field-label">
            Match Date <span className="text-slate-600">(optional)</span>
          </label>
          <input type="date" className="input" value={value.matchDate} onChange={set('matchDate')} />
        </div>
      </div>

      {/* Squads via SquadBuilder */}
      <SquadBuilder
        apiBase={apiBase}
        label={`${value.teamA || 'Team A'} Squad (optional)`}
        players={value.squadA}
        onChange={squadA => onChange({ ...value, squadA })}
        placeholder="Search & add players…"
      />
      <SquadBuilder
        apiBase={apiBase}
        label={`${value.teamB || 'Team B'} Squad (optional)`}
        players={value.squadB}
        onChange={squadB => onChange({ ...value, squadB })}
        placeholder="Search & add players…"
      />
    </div>
  )
}
