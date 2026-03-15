import { useState, useRef } from 'react'
import { callPlayerSearch } from '../lib/api'

interface Props {
  apiBase: string
  label: string
  players: string[]
  onChange: (players: string[]) => void
  placeholder?: string
  maxPlayers?: number
}

/**
 * Tag-based squad input. Type a name, pick from Cricsheet autocomplete,
 * and add up to maxPlayers (default 11) as removable tags.
 */
export default function SquadBuilder({
  apiBase,
  label,
  players,
  onChange,
  placeholder = 'Search player…',
  maxPlayers = 11,
}: Props) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [highlighted, setHighlighted] = useState(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const search = (q: string) => {
    setQuery(q)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (q.trim().length < 2) { setSuggestions([]); setOpen(false); return }
    debounceRef.current = setTimeout(() => {
      setLoading(true)
      callPlayerSearch(apiBase, q)
        .then(res => { setSuggestions(res); setOpen(res.length > 0); setHighlighted(-1) })        .catch(() => setSuggestions([]))
        .finally(() => setLoading(false))
    }, 300)
  }

  const addPlayer = (name: string) => {
    if (!players.includes(name) && players.length < maxPlayers) {
      onChange([...players, name])
    }
    setQuery('')
    setSuggestions([])
    setOpen(false)
  }

  const removePlayer = (name: string) => {
    onChange(players.filter(p => p !== name))
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setHighlighted(h => Math.min(h + 1, suggestions.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlighted(h => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter') {
      e.preventDefault()
      if (highlighted >= 0 && suggestions[highlighted]) addPlayer(suggestions[highlighted])
      else if (query.trim()) addPlayer(query.trim()) // allow free-text entry
    } else if (e.key === 'Escape') { setOpen(false) }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="field-label">{label}</label>
        <span className="text-[10px] text-slate-600">{players.length}/{maxPlayers}</span>
      </div>

      {/* Tags */}
      {players.length > 0 && (
        <div className="flex flex-wrap gap-1.5 p-2 rounded-xl min-h-[40px]"
          style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
          {players.map(name => (
            <span
              key={name}
              className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
              style={{ background: 'rgba(255,107,53,0.12)', color: '#ff6b35', border: '1px solid rgba(255,107,53,0.2)' }}
            >
              🏏 {name}
              <button
                type="button"
                onClick={() => removePlayer(name)}
                className="ml-0.5 text-slate-500 hover:text-red-400 transition-colors leading-none"
                aria-label={`Remove ${name}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Input + dropdown */}
      {players.length < maxPlayers && (
        <div className="relative">
          <div className="relative">
            <input
              className="input pr-8"
              placeholder={placeholder}
              value={query}
              onChange={e => search(e.target.value)}
              onFocus={() => { if (suggestions.length > 0) setOpen(true) }}
              onKeyDown={handleKeyDown}
              onBlur={() => setTimeout(() => setOpen(false), 150)}
              autoComplete="off"
            />
            {loading && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
                <svg className="w-4 h-4 animate-spin text-orange-400" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
              </span>
            )}
          </div>

          {open && suggestions.length > 0 && (
            <ul
              role="listbox"
              className="absolute z-50 w-full mt-1 rounded-xl overflow-hidden shadow-2xl"
              style={{
                background: 'rgba(10,15,35,0.97)',
                border: '1px solid rgba(255,107,53,0.25)',
                backdropFilter: 'blur(20px)',
                maxHeight: '200px',
                overflowY: 'auto',
              }}
            >
              {suggestions.map((name, i) => {
                const already = players.includes(name)
                return (
                  <li
                    key={name}
                    role="option"
                    aria-selected={i === highlighted}
                    onMouseDown={() => addPlayer(name)}
                    onMouseEnter={() => setHighlighted(i)}
                    className="flex items-center gap-3 px-4 py-2.5 cursor-pointer text-sm transition-colors"
                    style={{
                      background: i === highlighted ? 'rgba(255,107,53,0.12)' : 'transparent',
                      color: already ? '#475569' : i === highlighted ? '#ff6b35' : '#cbd5e1',
                      borderBottom: i < suggestions.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                    }}
                  >
                    <span className="text-base">{already ? '✓' : '🏏'}</span>
                    <span className="font-medium">{name}</span>
                    {already && <span className="ml-auto text-[10px] text-slate-600">already added</span>}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}

      <p className="text-[10px] text-slate-600 px-1">
        Search Cricsheet names (e.g. "V Kohli", "JJ Bumrah") — or type any name and press Enter
      </p>
    </div>
  )
}
