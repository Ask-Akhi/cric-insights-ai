/**
 * RecentForm — shows a player's last N innings/matches as coloured pip bars.
 * Batter: green=50+, amber=25–49, red=<25.  Bowler: green=2+W, amber=1W, red=0W.
 */
interface FormEntry {
  value: number   // runs (batter) or wickets (bowler)
  label: string   // e.g. "vs AUS" or match date
}

interface Props {
  entries: FormEntry[]
  type: 'bat' | 'bowl'
  className?: string
}

function pipColor(type: 'bat' | 'bowl', value: number): string {
  if (type === 'bat') {
    if (value >= 50) return '#4ade80'   // green — fifty+
    if (value >= 25) return '#fbbf24'   // amber — decent
    return '#f87171'                    // red — low
  }
  // bowl
  if (value >= 2) return '#4ade80'
  if (value >= 1) return '#fbbf24'
  return '#f87171'
}

function pipHeight(type: 'bat' | 'bowl', value: number): string {
  if (type === 'bat') {
    const h = Math.min(Math.round((value / 100) * 32) + 8, 40)
    return `${h}px`
  }
  const h = Math.min(Math.round((value / 4) * 32) + 8, 40)
  return `${h}px`
}

export default function RecentForm({ entries, type, className = '' }: Props) {
  if (!entries.length) return null
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <p className="text-[10px] text-slate-500 uppercase tracking-widest">
        Last {entries.length} {type === 'bat' ? 'innings' : 'matches'}
      </p>
      <div className="flex items-end gap-1.5 h-10">
        {entries.map((e, i) => (
          <div key={i} className="group flex flex-col items-center gap-0.5 relative flex-1 min-w-0">
            <div
              className="w-full rounded-sm transition-all"
              style={{
                background: pipColor(type, e.value),
                height: pipHeight(type, e.value),
                opacity: 0.85,
              }}
            />
            <span className="text-[9px] text-slate-500 truncate w-full text-center">
              {type === 'bat' ? `${e.value}` : `${e.value}W`}
            </span>
            {/* Tooltip */}
            <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[9px] px-1.5 py-0.5 rounded whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none z-10 transition-opacity">
              {e.label}: {type === 'bat' ? `${e.value} runs` : `${e.value} wickets`}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
