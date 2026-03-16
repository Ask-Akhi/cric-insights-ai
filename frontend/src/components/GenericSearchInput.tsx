import { useState, useRef } from 'react'

interface Props {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  onSearch: (q: string) => Promise<string[]>
  placeholder?: string
  icon?: string
}

/**
 * Reusable debounced autocomplete input backed by any async search function.
 */
export default function GenericSearchInput({
  id, label, value, onChange, onSearch, placeholder = 'Search…', icon = '🔍',
}: Props) {
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [highlighted, setHighlighted] = useState(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const search = (q: string) => {
    onChange(q)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (q.trim().length < 2) { setSuggestions([]); setOpen(false); return }
    debounceRef.current = setTimeout(() => {
      setLoading(true)
      onSearch(q)
        .then(res => { setSuggestions(res); setOpen(res.length > 0); setHighlighted(-1) })
        .catch(() => setSuggestions([]))
        .finally(() => setLoading(false))
    }, 280)
  }

  const pick = (name: string) => {
    onChange(name)
    setSuggestions([])
    setOpen(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setHighlighted(h => Math.min(h + 1, suggestions.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlighted(h => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter' && highlighted >= 0) { e.preventDefault(); pick(suggestions[highlighted]) }
    else if (e.key === 'Escape') setOpen(false)
  }
  return (
    <div className="relative">
      {label && <label htmlFor={id} className="field-label">{label}</label>}
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm pointer-events-none">{icon}</span>
        <input
          id={id}
          className="input pl-9"
          placeholder={placeholder}
          value={value}
          onChange={e => search(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onFocus={() => value.length >= 2 && suggestions.length > 0 && setOpen(true)}
          autoComplete="off"
        />
        {loading && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 text-xs animate-spin">⏳</span>
        )}
      </div>

      {open && suggestions.length > 0 && (
        <div
          className="absolute z-50 w-full mt-1 rounded-xl overflow-hidden shadow-2xl"
          style={{ background: '#0d1424', border: '1px solid rgba(255,255,255,0.1)' }}
        >
          {suggestions.map((s, i) => (
            <button
              key={s}
              type="button"
              onMouseDown={() => pick(s)}
              className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                i === highlighted ? 'bg-orange-500/20 text-orange-300' : 'text-slate-300 hover:bg-white/5'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
