import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AskIntent, AskMode } from '../lib/api'

interface Props {
  icon: string
  title: string
  subtitle?: string
  onSubmit: () => Promise<{ answer: string; intent?: AskIntent; players?: string[]; mode?: AskMode; data_sources?: string[] } | string>
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
  { ms: 0,    text: '🧠 Routing question...'         },
  { ms: 800,  text: '🔍 Fetching player stats...' },
  { ms: 2000, text: '⚙️  Running analysis node...'   },
  { ms: 4500, text: '✍️  Generating answer...'       },
  { ms: 8000, text: '🔄 Synthesizing response...'    },
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

// ── Splits raw markdown answer into [summary, rest] ─────────────────────────
// Rules:
//  1. Short answers (≤ 300 chars) → show everything, no expand.
//  2. Find the first clean paragraph break after ≥120 chars of content.
//  3. NEVER cut if the next block is a table/list/heading/bold-section-header.
//  4. NEVER cut if a table is within 12 non-blank lines ahead — prevents
//     orphaning intro sentences like "Here are the top performers:" that
//     belong with the table that follows.
//  5. NEVER cut if prevLine is a table row or table separator (| --- | --- |).
//  6. If no safe cut found → no split (show all).
function splitAnswer(raw: string): { summary: string; detail: string | null } {
  const text = raw.replace(/^⚡ \*\(cached\)\*\n\n/, '')

  if (text.length <= 300) return { summary: text, detail: null }

  const lines = text.split('\n')

  /** True if a line is a markdown table row (2+ pipe chars) */
  const isTableRow = (line: string) => (line.match(/\|/g) ?? []).length >= 2
  /** True if a line opens a structured block (list/heading/table/bold-section-header). */
  const isStructured = (line: string) => {
    const t = line.trim()
    if (t.startsWith('|')) return true             // table row
    if (t.startsWith('#')) return true             // ATX heading
    if (/^\d+\./.test(t)) return true              // numbered list
    if (/^\* \S/.test(t)) return true              // unordered list  (* item)
    if (/^- \S/.test(t)) return true               // unordered list  (- item)
    // Bold-only line used as a section header: **Key Factors** or **Player Predictions**
    if (/^\*\*[^*]+\*\*[:\s]*$/.test(t)) return true
    return false
  }

  /** True if a markdown table appears within `lookahead` non-blank lines of lineIdx */
  const tableComingUp = (lineIdx: number, lookahead = 12): boolean => {
    let seen = 0
    for (let j = lineIdx; j < lines.length && seen < lookahead; j++) {
      if (lines[j].trim() === '') continue
      if (isTableRow(lines[j])) return true
      seen++
    }
    return false
  }

  /** True if line is a markdown table separator (| --- | --- |) */
  const isTableSeparator = (line: string) =>
    /^\|[\s|:\-]+\|$/.test(line.trim())
  /** True if a line is a dangling intro — meaningless without what follows */
  const isIntroSentence = (line: string) => {
    const t = line.trim().toLowerCase()
    return (
      t.startsWith('here are') || t.startsWith('here is') ||
      t.startsWith('below are') || t.startsWith('below is') ||
      t.startsWith('the following') || t.startsWith('these are') ||
      t.startsWith('based on') || t.startsWith('see below')
    )
  }

  let cutLineIdx = -1

  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim() !== '') continue  // only act on blank lines

    let next = i + 1
    while (next < lines.length && lines[next].trim() === '') next++
    if (next >= lines.length) break

    const charsSoFar = lines.slice(0, i).join('\n').length
    if (charsSoFar < 120) continue  // need a real paragraph, not just one intro line

    const prevLine = lines[i - 1] ?? ''
    const nextLine = lines[next]

    if (isStructured(nextLine)) continue              // next block is structured
    if (tableComingUp(next, 12)) continue            // table within 12 non-blank lines
    if (isTableRow(prevLine)) continue              // we're inside a table row
    if (isTableSeparator(prevLine)) continue        // we're after a table separator
    if (prevLine.trim().startsWith('#')) continue   // right after a heading
    if (isIntroSentence(prevLine)) continue         // dangling intro — skip

    cutLineIdx = i
    break
  }

  if (cutLineIdx === -1) return { summary: text, detail: null }

  const summary = lines.slice(0, cutLineIdx).join('\n').trim()
  const detail  = lines.slice(cutLineIdx).join('\n').trim()
  if (!detail) return { summary: text, detail: null }
  return { summary, detail }
}

function AnswerBlock({ answer, isCached }: { answer: string; isCached: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const cleanAnswer = isCached ? answer.replace(/^⚡ \*\(cached\)\*\n\n/, '') : answer
  const { summary, detail } = splitAnswer(cleanAnswer)
  const hasMore = !!detail

  return (
    <div>
      <div className="prose-cricket">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{summary}</ReactMarkdown>
      </div>
      {hasMore && (
        <>
          <AnimatePresence>
            {expanded && (
              <motion.div
                key="detail"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                className="overflow-hidden"
              >
                <div className="prose-cricket mt-3 pt-3" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail!}</ReactMarkdown>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <button
            type="button"
            onClick={() => setExpanded(v => !v)}
            className="mt-3 flex items-center gap-1.5 text-[11px] font-semibold transition-all duration-200"
            style={{ color: expanded ? '#94a3b8' : '#ff6b35' }}
          >
            <motion.span
              animate={{ rotate: expanded ? 180 : 0 }}
              transition={{ duration: 0.2 }}
              className="inline-block"
            >
              ▼
            </motion.span>
            {expanded ? 'Show less' : 'Show more details'}
          </button>
        </>
      )}
    </div>
  )
}

export default function ToolShell({ icon, title, subtitle, onSubmit, onQuestionAsked, children, sidePanel, sidePanelReady }: Props) {
  const [loading, setLoading]         = useState(false)
  const [answer, setAnswer]           = useState<string | null>(null)
  const [intent, setIntent]           = useState<AskIntent>('general')
  const [players, setPlayers]         = useState<string[]>([])
  const [mode, setMode]               = useState<AskMode>('graph')
  const [dataSources, setDataSources] = useState<string[]>([])
  const [error, setError]             = useState<string | null>(null)
  const [elapsed, setElapsed]         = useState<number>(0)
  const [copied, setCopied]           = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setAnswer(null); setError(null); setElapsed(0); setLoading(true); setCopied(false); setDataSources([])
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
                        'Cricsheet RAG':       { icon: '📊', color: '#34d399' },
                        'Google Search':       { icon: '🌐', color: '#60a5fa' },
                        'Gemini training data':{ icon: '🧠', color: '#a78bfa' },
                        'LangGraph':           { icon: '✦',  color: '#a78bfa' },
                      }
                      const c = cfg[src] ?? { icon: '📁', color: '#94a3b8' }
                      return (
                        <span key={src} className="text-[9px] font-semibold px-1.5 py-0.5 rounded-md"
                          style={{ background: `${c.color}15`, color: c.color, border: `1px solid ${c.color}30` }}>
                          {c.icon} {src}
                        </span>
                      )
                    })}
                    {/* Detected players */}
                    {players.length > 0 && (
                      <span className="text-[9px] text-slate-500 font-medium">
                        👤 {players.join(', ')}
                      </span>
                    )}
                    {isCached && <span className="stat-badge stat-badge-gold">⚡ cached</span>}
                    <span className="ml-auto text-xs text-slate-600 font-mono">{(elapsed / 1000).toFixed(1)}s</span>
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
