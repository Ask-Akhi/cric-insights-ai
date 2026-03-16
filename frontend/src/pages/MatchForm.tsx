import React from 'react'
import SquadBuilder from '../components/SquadBuilder'
import GenericSearchInput from '../components/GenericSearchInput'
import { callVenueSearch, callTeamSearch } from '../lib/api'

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
        </div>      )}

      {/* Teams */}
      <div className="grid grid-cols-2 gap-4">
        <GenericSearchInput
          id="form-team-a"
          label="Team A"
          value={value.teamA}
          onChange={v => onChange({ ...value, teamA: v })}
          onSearch={q => callTeamSearch(apiBase, q)}
          placeholder="e.g. Mumbai Indians"
          icon="🏏"
        />
        <GenericSearchInput
          id="form-team-b"
          label="Team B"
          value={value.teamB}
          onChange={v => onChange({ ...value, teamB: v })}
          onSearch={q => callTeamSearch(apiBase, q)}
          placeholder="e.g. Chennai Super Kings"
          icon="🏏"
        />
      </div>

      {/* Venue + Date */}
      <div className="grid grid-cols-2 gap-4">
        <GenericSearchInput
          id="form-venue"
          label="Venue"
          value={value.venue}
          onChange={v => onChange({ ...value, venue: v })}
          onSearch={q => callVenueSearch(apiBase, q)}
          placeholder="e.g. Wankhede Stadium"
          icon="🏟️"
        />
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
