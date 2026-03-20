import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import type { AskIntent, AskMode } from '../lib/api'

interface Props {
  icon: string
  title: string
  subtitle?: string
  onSubmit: () => Promise<{ answer: string; intent?: AskIntent; players?: string[]; mode?: AskMode } | string>
  children: React.ReactNode
  sidePanel?: React.ReactNode
  sidePanelReady?: boolean
}

// ── Intent badge config ────────────────────────────────────────────────────
const INTENT_CONFIG: Record<AskIntent, { label: string; color: string; bg: string }> = {
  stats:   { label: '📊 Stats',      color: '#60a5fa', bg: 'rgba(96,165,250,0.12)'  },
  compare: { label: '⚖️ Compare',    color: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
  fantasy: { label: '🏆 Fantasy',    color: '#fbbf24', bg: 'rgba(251,191,36,0.12)'  },
  predict: { label: '🔮 Predict',    color: '#34d399', bg: 'rgba(52,211,153,0.12)'  },
  general: { label: '💬 General',    color: '#ff6b35', bg: 'rgba(255,107,53,0.12)'  },
}

// ── Thinking steps shown during graph execution ────────────────────────────
const THINKING_STEPS = [
  { ms: 0,    text: '🧠 Routing question...'             },
  { ms: 800,  text: '🔍 Fetching Cricsheet stats...'     },
  { ms: 2000, text: '⚙️  Running analysis node...'       },
  { ms: 4500, text: '✍️  Generating answer...'           },
  { ms: 8000, text: '🔄 Synthesizing response...'        },
]

function ThinkingSteps({ elapsed }: { elapsed: number }) {
  const visible = THINKING_STEPS.filter(s => elapsed >= s.ms)
  return (
    <div className="space-y-2 py-1">
      {visible.map((s, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3 }}
          className="flex items-center gap-2 text-xs"
        >
          <span className="text-slate-400">{s.text}</span>
          {i === visible.length - 1 && (
            <span className="inline-flex gap-0.5 ml-1">
              {[0,1,2].map(d => (
                <motion.span key={d} className="w-1 h-1 rounded-full bg-orange-400"
                  animate={{ opacity: [0.3,1,0.3] }}
                  transition={{ duration: 0.9, delay: d * 0.2, repeat: Infinity }} />
              ))}
            </span>
          )}
        </motion.div>
      ))}
    </div>
  )
}

function ModeBadge({ mode }: { mode: AskMode }) {
  const cfg: Record<AskMode, { label: string; color: string }> = {
    graph:    { label: 'LangGraph ✦', color: '#a78bfa' },
    direct:   { label: 'Direct LLM',  color: '#60a5fa' },
    fallback: { label: 'Fallback',    color: '#f87171' },
    grounded: { label: '🌐 Grounded', color: '#34d399' },
  }
  const c = cfg[mode] ?? cfg.direct
  return (
    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md tracking-wide"
      style={{ background: `${c.color}18`, color: c.color, border: `1px solid ${c.color}30` }}>
      {c.label}
    </span>
  )
}

export default function ToolShell({ icon, title, subtitle, onSubmit, children, sidePanel, sidePanelReady }: Props) {
  const [loading, setLoading]   = useState(false)
  const [answer, setAnswer]     = useState<string | null>(null)
  const [intent, setIntent]     = useState<AskIntent>('general')
  const [players, setPlayers]   = useState<string[]>([])
  const [mode, setMode]         = useState<AskMode>('graph')
  const [error, setError]       = useState<string | null>(null)
  const [elapsed, setElapsed]   = useState<number>(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setAnswer(null); setError(null); setElapsed(0); setLoading(true)
    const start = Date.now()
    timerRef.current = setInterval(() => setElapsed(Date.now() - start), 100)
    try {
      const result = await onSubmit()
      if (typeof result === 'string') {
        setAnswer(result)
      } else {
        setAnswer(result.answer)
        setIntent(result.intent ?? 'general')
        setPlayers(result.players ?? [])
        setMode(result.mode ?? 'graph')
      }
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setLoading(false)
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }

  const isCached   = answer?.startsWith('⚡')
  const showSide   = sidePanel && sidePanelReady
  const hasResult  = loading || answer || error
  const intentCfg  = INTENT_CONFIG[intent]

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div className="flex items-start gap-4">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl flex-shrink-0 animate-float"
          style={{ background: 'linear-gradient(135deg, rgba(255,107,53,0.2), rgba(255,85,0,0.08))', border: '1px solid rgba(255,107,53,0.25)' }}>
          {icon}
        </div>
        <div className="pt-1">
          <h2 className="text-2xl font-bold text-white leading-tight tracking-tight" style={{ fontFamily: '"Playfair Display", Georgia, serif' }}>
            {title}
          </h2>
          {subtitle && <p className="text-sm text-slate-500 mt-1 leading-relaxed">{subtitle}</p>}
        </div>
      </div>

      {/* ── Form Card ── */}
      <div className="glass-strong p-6 space-y-5">
        <form onSubmit={handleSubmit} className="space-y-4">
          {children}
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? (
              <>
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
                </svg>
                Analysing… {(elapsed / 1000).toFixed(1)}s
              </>
            ) : <>{icon} Analyse</>}
          </button>
        </form>
      </div>

      {/* ── Result area ── */}
      <AnimatePresence>
        {hasResult && (
          <motion.div key="result-area"
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className={showSide ? 'grid grid-cols-1 lg:grid-cols-2 gap-5 items-start' : ''}
          >
            {/* ── Left: AI text ── */}
            <div className="glass p-6">
              {loading ? (
                <>
                  <div className="flex items-center gap-2 mb-5 pb-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    <span className="text-orange-400 text-xs font-semibold tracking-wide uppercase">
                      Running LangGraph Pipeline
                    </span>
                    <span className="text-xs text-slate-600 ml-auto font-mono">{(elapsed / 1000).toFixed(1)}s</span>
                  </div>
                  <ThinkingSteps elapsed={elapsed} />
                </>
              ) : error ? (
                <div className="flex items-start gap-3 text-sm">
                  {error.includes('API_KEY') || error.includes('not configured') ? (
                    <div className="w-full rounded-xl p-4 space-y-2" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)' }}>
                      <p className="text-red-400 font-semibold">⚙️ API Key Not Configured</p>
                      <p className="text-slate-400 text-xs leading-relaxed">
                        Set <code className="text-orange-300">GEMINI_API_KEY</code> in Railway → Variables.
                      </p>
                    </div>
                  ) : (
                    <><span className="text-lg flex-shrink-0 text-red-400">❌</span><span className="text-red-400">{error}</span></>
                  )}
                </div>
              ) : answer ? (
                <>
                  {/* ── Result header with badges ── */}
                  <div className="flex items-center gap-2 mb-5 pb-4 flex-wrap" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    <span className="text-[10px] font-bold tracking-widest uppercase text-orange-400">💡 AI Analysis</span>
                    {/* Intent badge */}
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md tracking-wide"
                      style={{ background: intentCfg.bg, color: intentCfg.color, border: `1px solid ${intentCfg.color}30` }}>
                      {intentCfg.label}
                    </span>
                    {/* Mode badge */}
                    <ModeBadge mode={mode} />
                    {/* Detected players */}
                    {players.length > 0 && (
                      <span className="text-[9px] text-slate-500 font-medium">
                        👤 {players.join(', ')}
                      </span>
                    )}
                    {isCached && <span className="stat-badge stat-badge-gold">⚡ cached</span>}
                    <span className="ml-auto text-xs text-slate-600 font-mono">{(elapsed / 1000).toFixed(1)}s</span>
                  </div>

                  <div className="prose-cricket">
                    <ReactMarkdown>
                      {isCached ? answer.replace(/^⚡ \*\(cached\)\*\n\n/, '') : answer}
                    </ReactMarkdown>
                  </div>
                  <div className="flex items-center justify-end gap-2 mt-5 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                    <button className="btn-ghost" onClick={() => { setAnswer(null); setError(null) }}>↩ Clear</button>
                  </div>
                </>
              ) : null}
            </div>

            {/* ── Right: side panel ── */}
            {showSide && <div className="glass p-6">{sidePanel}</div>}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
