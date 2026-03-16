import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import { callAsk } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

const CHIP_CATEGORIES = [
  {
    label: '🏏 Batting',
    chips: [
      "Who are the top 5 batters in {format} cricket right now?",
      "What is Virat Kohli's average in {format} matches in the last 2 years?",
      "Which batter has the best strike rate in T20 death overs (16-20)?",
      "Compare Rohit Sharma and Joe Root across all formats.",
    ],
  },
  {
    label: '🎳 Bowling',
    chips: [
      "Who are the most economical bowlers in {format} powerplay overs?",
      "Which spinners are best on turning tracks in {format}?",
      "Best bowling attacks in {format} cricket currently?",
      "Who takes the most wickets in the death overs in {format}?",
    ],
  },
  {
    label: '🏆 Fantasy',
    chips: [
      "Give me a fantasy XI for India vs Australia in {format} at the MCG.",
      "Which differential picks should I consider for my fantasy team today?",
      "Best captain choices for India's next {format} match?",
      "Suggest a balanced fantasy team for a pitch favoring spinners.",
    ],
  },
  {
    label: '🏟️ Venue & Tactics',
    chips: [
      "What is the average score at Wankhede Stadium in {format} cricket?",
      "Which teams perform best chasing at Lord's in Tests?",
      "What tactics work best at Eden Gardens in {format}?",
      "Does the toss matter at Chepauk in Test matches?",
    ],
  },
]

export default function AskAI({ apiBase, format, grounded }: Props) {
  const [question, setQuestion] = useState('')
  const [activeCategory, setActiveCategory] = useState(0)

  const handleChip = (chip: string) => {
    setQuestion(chip.replace(/\{format\}/g, format))
  }

  return (
    <ToolShell
      icon="💬"
      title="Ask the Cricket AI"
      subtitle="Free-form cricket questions — stats, fantasy, predictions, tactics"
      onSubmit={() => callAsk(apiBase, {
        prompt: question,
        context: { format },
        grounded,
      })}
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
                  background: isActive
                    ? 'rgba(255,107,53,0.12)'
                    : 'rgba(255,255,255,0.02)',
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
        </p>
      </div>
    </ToolShell>
  )
}
