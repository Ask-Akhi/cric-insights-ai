import { useState, useEffect, useRef } from 'react'
import ToolShell from '../components/ToolShell'
import PlayerCharts from '../components/PlayerCharts'
import { callAsk, callPlayerStats, callPlayerDetect, PlayerStats } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean; onQuestionAsked?: () => void }

/** Debounce helper — returns a value that only updates after `delay` ms of quiet. */
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return debounced
}

const CHIP_CATEGORIES = [
  {
    label: '🏏 Batting',
    chips: [
      "Virat Kohli's {format} average in the last 2 years?",
      "Top 5 {format} batters by strike rate right now",
      "Rohit Sharma vs Babar Azam in {format} — who is better?",
      "Which batter has the best death-over strike rate (16-20) in {format}?",
    ],
  },
  {
    label: '🎳 Bowling',
    chips: [
      "Jasprit Bumrah's {format} economy and wickets this season",
      "Best spinners on turning tracks in {format} — ranked",
      "Which pacer has the best powerplay economy in {format}?",
      "Rashid Khan vs Wanindu Hasaranga — compare in {format}",
    ],
  },
  {
    label: '🏆 Fantasy',
    chips: [
      "Best captain picks for MI vs CSK in {format}",
      "Top differential picks for {format} fantasy this week",
      "Safe no-brainer picks for {format} fantasy — low risk",
      "Fantasy XI for India vs Australia at Wankhede in {format}",
    ],
  },
  {
    label: '🔮 Predict',
    chips: [
      "Who will win IPL 2026 — predict with confidence %",
      "India vs Australia {format} — who wins and why?",
      "Which team has the best chance of winning the {format} World Cup?",
      "Predict the top run-scorer in IPL 2026",
    ],
  },
  {
    label: '🏟️ Venue',
    chips: [
      "Average score at Wankhede in {format} — pitch report",
      "Best bowling venues for pacers in {format} cricket",
      "Does the toss matter at Chepauk in Test matches?",
      "Eden Gardens {format} stats — batting or bowling pitch?",
    ],
  },
]

export default function AskAI({ apiBase, format, grounded, onQuestionAsked }: Props) {
  const [question, setQuestion] = useState('')
  const [activeCategory, setActiveCategory] = useState(0)
  const [chartData, setChartData] = useState<PlayerStats | null>(null)
  const [chartLoading, setChartLoading] = useState(false)
  const [chartPlayer, setChartPlayer] = useState<string | null>(null)

  // ── Live player detection via backend API (debounced, no hardcoded list) ──
  const debouncedQ = useDebounced(question, 400)
  const lastDetectRef = useRef<string>('')
  useEffect(() => {
    if (debouncedQ.length < 6 || debouncedQ === lastDetectRef.current) return
    lastDetectRef.current = debouncedQ
    // Use the lightweight /detect endpoint — aliases scan, no Cricsheet I/O
    callPlayerDetect(apiBase, debouncedQ)
      .then(players => {
        if (players.length > 0 && debouncedQ === lastDetectRef.current) {
          const name = players[0]
          setChartPlayer(name)
          setChartData(null)
          setChartLoading(true)
          callPlayerStats(apiBase, name, format)
            .then(setChartData)
            .catch(() => setChartData(null))
            .finally(() => setChartLoading(false))
        } else if (players.length === 0) {
          // Clear side panel only if question changed enough to warrant it
          setChartPlayer(null)
          setChartData(null)
        }
      })
      .catch(() => { /* silent — don't disrupt typing */ })
  }, [debouncedQ, apiBase, format])

  const handleChip = (chip: string) => {
    setQuestion(chip.replace(/\{format\}/g, format))
  }

  const handleSubmit = async () => {
    // Use players list returned by the AI response to confirm/update chart player
    const result = await callAsk(apiBase, {
      prompt: question,
      context: { format },
      grounded,
    })

    // If the AI response identified player(s) and we haven't loaded charts yet, fetch now
    if (result.players?.length > 0) {
      const name = result.players[0]
      if (name !== chartPlayer) {
        setChartPlayer(name)
        setChartData(null)
        setChartLoading(true)
        callPlayerStats(apiBase, name, format)
          .then(setChartData)
          .catch(() => setChartData(null))
          .finally(() => setChartLoading(false))
      }
    }

    return result
  }

  // Side panel shown when a player was detected
  const chartsPanel = chartPlayer ? (
    <>
      <div className="flex items-center gap-2 mb-4 pb-3" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <span className="text-[10px] font-bold tracking-widest uppercase text-amber-400">📊 Player Data — {chartPlayer}</span>
        {chartLoading && <span className="ml-auto text-[10px] text-slate-500 animate-pulse">Loading…</span>}
      </div>
      {chartLoading && (
        <div className="space-y-3">
          <div className="shimmer-line h-20 w-full rounded-xl" />
          <div className="shimmer-line h-4 w-2/3" />
          <div className="shimmer-line h-32 w-full rounded-xl" />
        </div>
      )}
      {!chartLoading && chartData?.found && <PlayerCharts stats={chartData} />}
      {!chartLoading && chartData && !chartData.found && (
        <p className="text-xs text-slate-500 text-center py-6">
          No Cricsheet data found for <strong className="text-slate-300">{chartPlayer}</strong>
        </p>
      )}
    </>
  ) : undefined
  return (
    <ToolShell
      icon="💬"
      title="Ask the Cricket AI"
      subtitle="Free-form cricket questions — stats, fantasy, predictions, tactics"
      onSubmit={handleSubmit}
      onQuestionAsked={onQuestionAsked}
      sidePanel={chartsPanel}
      sidePanelReady={(chartLoading || !!chartData) && !!chartPlayer}
    >
      {/* ── Suggested prompts ──────────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="field-label mb-0">Suggested Questions</label>
          <span className="text-[10px] text-slate-600 uppercase tracking-widest">Click to use</span>
        </div>

        {/* Category tabs */}
        <div className="flex gap-1.5 flex-wrap">
          {CHIP_CATEGORIES.map((cat, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setActiveCategory(i)}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-all duration-200 ${
                activeCategory === i
                  ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                  : 'text-slate-500 border border-white/[0.06] hover:border-white/10 hover:text-slate-400'
              }`}
              style={{ background: activeCategory === i ? undefined : 'rgba(255,255,255,0.03)' }}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Chips */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {CHIP_CATEGORIES[activeCategory].chips.map((chip, i) => {
            const display = chip.replace(/\{format\}/g, format)
            const isActive = question === display
            return (
              <button
                key={i}
                type="button"
                onClick={() => handleChip(chip)}
                className="text-left px-3 py-2.5 rounded-xl text-xs leading-snug transition-all duration-200"
                style={{
                  background: isActive ? 'rgba(255,107,53,0.12)' : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${isActive ? 'rgba(255,107,53,0.35)' : 'rgba(255,255,255,0.06)'}`,
                  color: isActive ? '#ff6b35' : '#94a3b8',
                }}
                onMouseEnter={e => {
                  if (!isActive) {
                    (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.04)'
                    ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.12)'
                    ;(e.currentTarget as HTMLButtonElement).style.color = '#e2e8f0'
                  }
                }}
                onMouseLeave={e => {
                  if (!isActive) {
                    (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.02)'
                    ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.06)'
                    ;(e.currentTarget as HTMLButtonElement).style.color = '#94a3b8'
                  }
                }}
              >
                {display}
              </button>
            )
          })}
        </div>
      </div>

      <div className="section-divider" />

      {/* ── Textarea ───────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="field-label mb-0">Your Question</label>
          {question && (
            <button
              type="button"
              onClick={() => setQuestion('')}
              className="text-[10px] text-slate-600 hover:text-slate-400 transition-colors"
            >
              ✕ Clear
            </button>
          )}
        </div>
        <textarea
          className="input h-28 resize-none"
          placeholder="Ask anything about cricket — or click a suggestion above…"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          required
        />
        <p className="text-[10px] text-slate-600 mt-1.5">
          {grounded ? '🌐 Live web search enabled · ' : '📚 Using historical data · '}
          Format context: <span className="text-orange-400 font-semibold">{format}</span>
          {chartPlayer && <> · <span className="text-amber-400">📊 Auto-loading charts for <strong>{chartPlayer}</strong></span></>}
        </p>
      </div>
    </ToolShell>
  )
}
