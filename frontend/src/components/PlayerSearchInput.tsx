import { useState, useEffect, useRef, useCallback } from 'react'
import { callPlayerSearchFull } from '../lib/api'

interface Props {
  apiBase: string
  value: string
  onChange: (val: string) => void
  placeholder?: string
  label?: string
  id?: string
}

/**
 * A player search input with debounced autocomplete from Cricsheet data.
 * Uses /api/players/search?q=... — alias hits shown with ⚡ indicator.
 */
export default function PlayerSearchInput({
  apiBase,
  value,
  onChange,
  placeholder = 'e.g. Rohit Sharma or RG Sharma',
  label = 'Player Name',
  id = 'player-search',
}: Props) {
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [aliasCount, setAliasCount]   = useState(0)
  const [open, setOpen]               = useState(false)
  const [loading, setLoading]         = useState(false)
  const [highlighted, setHighlighted] = useState(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const fetchSuggestions = useCallback(
    (q: string) => {
      if (q.trim().length < 2) {
        setSuggestions([])
        setAliasCount(0)
        setOpen(false)
        return
      }
      setLoading(true)
      callPlayerSearchFull(apiBase, q)
        .then(result => {
          setSuggestions(result.players)
          setAliasCount(result.sources?.alias_hits ?? 0)
          setOpen(result.players.length > 0)
          setHighlighted(-1)
        })
        .catch(() => { setSuggestions([]); setAliasCount(0) })
        .finally(() => setLoading(false))
    },
    [apiBase],
  )

  // Debounce search by 300 ms
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => fetchSuggestions(value), 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [value, fetchSuggestions])

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const select = (name: string) => {
    onChange(name)
    setOpen(false)
    setSuggestions([])
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted(h => Math.min(h + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted(h => Math.max(h - 1, 0))
    } else if (e.key === 'Enter' && highlighted >= 0) {
      e.preventDefault()
      select(suggestions[highlighted])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <label htmlFor={id} className="field-label">{label}</label>

      <div className="relative">
        <input
          id={id}
          className="input pr-8"
          placeholder={placeholder}
          value={value}
          onChange={e => { onChange(e.target.value); setOpen(true) }}
          onFocus={() => { if (suggestions.length > 0) setOpen(true) }}
          onKeyDown={handleKeyDown}
          autoComplete="off"
        />
        {/* spinner / check icon */}
        <span className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
          {loading ? (
            <svg className="w-4 h-4 animate-spin text-orange-400" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
          ) : value && suggestions.length === 0 && value.trim().length >= 2 ? (
            <svg className="w-4 h-4 text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
            </svg>
          ) : null}
        </span>
      </div>

      {/* Dropdown */}
      {open && suggestions.length > 0 && (
        <ul
          role="listbox"
          className="absolute z-50 w-full mt-1 rounded-xl overflow-hidden shadow-2xl"
          style={{
            background: 'rgba(10,15,35,0.97)',
            border: '1px solid rgba(255,107,53,0.25)',
            backdropFilter: 'blur(20px)',
            maxHeight: '220px',
            overflowY: 'auto',
          }}
        >      {suggestions.map((name, i) => (
            <li
              key={name}
              role="option"
              aria-selected={i === highlighted}
              onMouseDown={() => select(name)}
              onMouseEnter={() => setHighlighted(i)}
              className="flex items-center gap-3 px-4 py-2.5 cursor-pointer text-sm transition-colors"
              style={{
                background: i === highlighted ? 'rgba(255,107,53,0.12)' : 'transparent',
                color: i === highlighted ? '#ff6b35' : '#cbd5e1',
                borderBottom: i < suggestions.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none',
              }}
            >
              <span className="text-base">🏏</span>
              <span className="font-medium flex-1">{name}</span>
              {i < aliasCount && (
                <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded-md flex-shrink-0"
                  style={{ background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.2)' }}
                  title="Matched via player alias — instant result">
                  ⚡ alias
                </span>
              )}
            </li>
          ))}
        </ul>
      )}      {/* Hint text */}
      <p className="text-[10px] text-slate-600 mt-1.5 px-1">
        Type a full name (e.g. "Virat Kohli") or initials (e.g. "V Kohli")
      </p>
    </div>
  )
}
