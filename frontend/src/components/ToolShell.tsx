import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AskIntent, AskMode } from '../lib/api'

interface Props {
  icon: string
  title: string
  subtitle?: string
  onSubmit: () => Promise<{ answer: string; intent?: AskIntent; players?: string[]; mode?: AskMode; data_sources?: string[]; latency_ms?: number; rag_cache_hit?: boolean } | string>
  onQuestionAsked?: () => void
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
  { ms: 0,    text: '🏏 Understanding your question…'  },
  { ms: 800,  text: '📊 Loading cricket data…'         },
  { ms: 2000, text: '🔍 Analysing stats & form…'       },
  { ms: 4500, text: '✍️  Crafting your answer…'        },
  { ms: 8000, text: '🎯 Finalising insights…'          },
]

function ThinkingSteps({ elapsed }: { elapsed: number }) {
  const visible = THINKING_STEPS.filter(s => elapsed >= s.ms)
  const sec = (elapsed / 1000).toFixed(1)
  return (
    <div className="space-y-2 py-1">
      {visible.map((s, i) => (
        <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3 }} className="flex items-center gap-2 text-xs">
          <span className="text-slate-400">{s.text}</span>
          {i === visible.length - 1 && (
            <>
              <span className="inline-flex gap-0.5 ml-1">
                {[0,1,2].map(d => (
                  <motion.span key={d} className="w-1 h-1 rounded-full bg-orange-400"
                    animate={{ opacity: [0.3,1,0.3] }}
                    transition={{ duration: 0.9, delay: d * 0.2, repeat: Infinity }} />
                ))}
              </span>
              <span className="ml-auto text-[10px] text-slate-600 font-mono tabular-nums">{sec}s</span>
            </>
          )}
        </motion.div>
      ))}
    </div>
  )
}

function ModeBadge({ mode }: { mode: AskMode }) {
  const cfg: Record<AskMode, { label: string; color: string }> = {
    graph:    { label: '✦ Deep Analysis', color: '#a78bfa' },
    direct:   { label: '⚡ Quick Answer', color: '#60a5fa' },
    fallback: { label: '🔄 Fallback',     color: '#f87171' },
    grounded: { label: '🌐 Web-grounded', color: '#34d399' },
  }
  const c = cfg[mode] ?? cfg.direct
  return (
    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md tracking-wide"
      style={{ background: `${c.color}18`, color: c.color, border: `1px solid ${c.color}30` }}>
      {c.label}
    </span>
  )
}

function AnswerBlock({ answer, isCached }: { answer: string; isCached: boolean }) {
  const cleanAnswer = isCached ? answer.replace(/^⚡ \*\(cached\)\*\n\n/, '') : answer
  return (
    <div className="prose-cricket">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanAnswer}</ReactMarkdown>
    </div>
  )
}

export default function ToolShell({ icon, title, subtitle, onSubmit, onQuestionAsked, children, sidePanel, sidePanelReady }: Props) {  const [loading, setLoading]         = useState(false)
  const [answer, setAnswer]           = useState<string | null>(null)
  const [intent, setIntent]           = useState<AskIntent>('general')
  const [players, setPlayers]         = useState<string[]>([])
  const [mode, setMode]               = useState<AskMode>('graph')
  const [dataSources, setDataSources] = useState<string[]>([])
  const [error, setError]             = useState<string | null>(null)
  const [elapsed, setElapsed]         = useState<number>(0)
  const [copied, setCopied]           = useState(false)
  const [serverLatency, setServerLatency] = useState<number | null>(null)
  const [ragCacheHit, setRagCacheHit]     = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setAnswer(null); setError(null); setElapsed(0); setLoading(true); setCopied(false)
    setDataSources([]); setServerLatency(null); setRagCacheHit(false)
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
        setDataSources(result.data_sources ?? [])
        setServerLatency(result.latency_ms ?? null)
        setRagCacheHit(result.rag_cache_hit ?? false)
      }
      onQuestionAsked?.()
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
  const showEmpty  = !hasResult

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

      {/* ── Empty state — shown before first query ── */}
      {showEmpty && (
        <div className="glass p-6 flex flex-col items-center text-center gap-3 animate-fade-in"
          style={{ border: '1px dashed rgba(255,255,255,0.07)' }}>
          <div className="text-4xl opacity-30">{icon}</div>
          <div>
            <p className="text-sm font-semibold text-slate-400">Fill in the details above and hit <span className="text-orange-400">Analyse</span></p>
            <p className="text-xs text-slate-600 mt-1">Results will appear here — powered by ball-by-ball cricket data + Gemini AI</p>
          </div>
          <div className="flex flex-wrap justify-center gap-2 mt-1">
            {(['📊 Ball-by-ball stats', '🌐 Web-grounded answers', '🏆 Fantasy scoring'].map(t => (
              <span key={t} className="text-[10px] px-2.5 py-1 rounded-full text-slate-600"
                style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
                {t}
              </span>
            )))}
          </div>        </div>
      )}

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
                  <div className="flex items-center gap-2 mb-5 pb-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>                    <span className="text-orange-400 text-xs font-semibold tracking-wide uppercase">
                      Preparing your insights…
                    </span>
                    <span className="text-xs text-slate-600 ml-auto font-mono">{(elapsed / 1000).toFixed(1)}s</span>
                  </div>
                  <ThinkingSteps elapsed={elapsed} />
                </>              ) : error ? (
                <div className="flex items-start gap-3 text-sm">
                  {error.includes('API_KEY') || error.includes('not configured') ? (
                    <div className="w-full rounded-xl p-4 space-y-2" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)' }}>
                      <p className="text-red-400 font-semibold">⚙️ API Key Not Configured</p>
                      <p className="text-slate-400 text-xs leading-relaxed">
                        Set <code className="text-orange-300">GEMINI_API_KEY</code> in Railway → Variables.
                      </p>
                    </div>
                  ) : error.includes('timed out') || error.includes('503') || error.includes('busy') ? (
                    <div className="w-full rounded-xl p-4 space-y-3" style={{ background: 'rgba(251,191,36,0.07)', border: '1px solid rgba(251,191,36,0.2)' }}>
                      <p className="text-yellow-400 font-semibold">⏱ AI is taking too long</p>
                      <p className="text-slate-400 text-xs leading-relaxed">
                        The AI service is busy or the question is too complex for the current timeout.
                      </p>
                      <ul className="text-slate-500 text-xs space-y-1 list-none">
                        <li>• Try a <strong className="text-slate-400">shorter, more specific question</strong></li>
                        <li>• Disable <strong className="text-slate-400">Live web search</strong> for faster answers</li>
                        <li>• Or click Retry — the response may already be cached</li>
                      </ul>
                      <button
                        className="btn-primary text-xs py-1.5 px-4 mt-1"
                        onClick={() => { setError(null); document.querySelector('form button[type="submit"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true })) }}
                      >
                        🔄 Retry
                      </button>
                    </div>
                  ) : (
                    <><span className="text-lg flex-shrink-0 text-red-400">❌</span><span className="text-red-400">{error}</span></>
                  )}
                </div>
              ) : answer ? (
                <>                  {/* ── Result header with badges ── */}
                  <div className="flex items-center gap-2 mb-5 pb-4 flex-wrap" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    <span className="text-[10px] font-bold tracking-widest uppercase text-orange-400">💡 AI Analysis</span>
                    {/* Intent badge */}
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md tracking-wide"
                      style={{ background: intentCfg.bg, color: intentCfg.color, border: `1px solid ${intentCfg.color}30` }}>
                      {intentCfg.label}
                    </span>
                    {/* Mode badge */}
                    <ModeBadge mode={mode} />
                    {/* Data source badges — shows exactly what data was used */}
                    {dataSources.map(src => {
                      const cfg: Record<string, { icon: string; color: string }> = {
                        'Cricsheet RAG':        { icon: '📊', color: '#34d399' },
                        'Google Search':        { icon: '🌐', color: '#60a5fa' },
                        'Gemini training data': { icon: '🧠', color: '#a78bfa' },
                        'LangGraph':            { icon: '✦',  color: '#a78bfa' },
                      }
                      // Friendly display labels for internal source names
                      const friendlyLabel: Record<string, string> = {
                        'Cricsheet RAG':        'Ball-by-ball data',
                        'Google Search':        'Live web search',
                        'Gemini training data': 'AI knowledge',                        'LangGraph':            'Deep analysis',
                      }
                      const c = cfg[src] ?? { icon: '📁', color: '#94a3b8' }
                      const label = friendlyLabel[src] ?? src
                      return (
                        <span key={src} className="text-[9px] font-semibold px-1.5 py-0.5 rounded-md"
                          style={{ background: `${c.color}15`, color: c.color, border: `1px solid ${c.color}30` }}>
                          {c.icon} {label}
                        </span>
                      )
                    })}
                    {/* Detected players */}
                    {players.length > 0 && (
                      <span className="text-[9px] text-slate-500 font-medium">
                        👤 {players.join(', ')}
                      </span>
                    )}                    {isCached && <span className="stat-badge stat-badge-gold">⚡ cached</span>}
                    {ragCacheHit && !isCached && (
                      <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded-md"
                        style={{ background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.25)' }}>
                        ⚡ RAG cached
                      </span>
                    )}
                    <span className="ml-auto flex items-center gap-2 text-xs text-slate-600 font-mono">
                      {serverLatency !== null && (
                        <span title="Server-side processing time" className="text-[10px] text-slate-600">
                          🖥 {(serverLatency / 1000).toFixed(1)}s
                        </span>
                      )}
                      <span title="Round-trip time">{(elapsed / 1000).toFixed(1)}s</span>
                    </span>
                  </div><AnswerBlock answer={answer} isCached={!!isCached} /><div className="flex items-center justify-end gap-2 mt-5 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>                    <button
                      className="btn-ghost"
                      onClick={() => {
                        const text = isCached ? answer!.replace(/^⚡ \*\(cached\)\*\n\n/, '') : answer!
                        navigator.clipboard.writeText(text).then(() => {
                          setCopied(true)
                          setTimeout(() => setCopied(false), 2000)
                        })
                      }}
                    >
                      {copied ? '✅ Copied!' : '📋 Copy full'}
                    </button>
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
