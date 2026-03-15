import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'

interface Props {
  icon: string
  title: string
  subtitle?: string
  onSubmit: () => Promise<string>
  children: React.ReactNode
}

function LoadingSkeleton() {
  return (
    <div className="space-y-3 py-2 animate-fade-in">
      <div className="shimmer-line h-4 w-3/4" />
      <div className="shimmer-line h-4 w-full" />
      <div className="shimmer-line h-4 w-5/6" />
      <div className="shimmer-line h-4 w-2/3 mt-4" />
      <div className="shimmer-line h-4 w-full" />
      <div className="shimmer-line h-4 w-4/5" />
      <div className="shimmer-line h-4 w-3/4 mt-4" />
      <div className="shimmer-line h-4 w-full" />
    </div>
  )
}

export default function ToolShell({ icon, title, subtitle, onSubmit, children }: Props) {
  const [loading, setLoading] = useState(false)
  const [answer, setAnswer]   = useState<string | null>(null)
  const [error, setError]     = useState<string | null>(null)
  const [elapsed, setElapsed] = useState<number>(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setAnswer(null)
    setError(null)
    setElapsed(0)
    setLoading(true)
    const start = Date.now()
    timerRef.current = setInterval(() => setElapsed(Date.now() - start), 100)
    try {
      const result = await onSubmit()
      setAnswer(result)
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setLoading(false)
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }

  const isCached = answer?.startsWith('⚡')

  return (
    <div className="space-y-5">

      {/* ── Tool Header ─────────────────────────────────────── */}
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

      {/* ── Form Card ───────────────────────────────────────── */}
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
            ) : (
              <>{icon} Analyse</>
            )}
          </button>
        </form>
      </div>

      {/* ── Result ──────────────────────────────────────────── */}
      <AnimatePresence>
        {loading && (
          <motion.div
            key="skeleton"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="glass p-6"
          >
            <div className="flex items-center gap-2 mb-5 pb-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <span className="text-orange-400 text-xs font-semibold tracking-wide uppercase">Generating Analysis</span>
              <span className="text-xs text-slate-600 ml-auto font-mono">{(elapsed / 1000).toFixed(1)}s</span>
            </div>
            <LoadingSkeleton />
          </motion.div>
        )}

        {!loading && (answer || error) && (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="glass p-6"
          >            {error ? (
              <div className="flex items-start gap-3 text-sm">
                {error.includes('GEMINI_API_KEY') || error.includes('OPENAI_API_KEY') || error.includes('not configured') ? (
                  <div className="w-full rounded-xl p-4 space-y-2" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)' }}>
                    <p className="text-red-400 font-semibold">⚙️ API Key Not Configured</p>
                    <p className="text-slate-400 text-xs leading-relaxed">
                      The <code className="text-orange-300">GEMINI_API_KEY</code> environment variable is missing.<br />
                      Go to <strong className="text-white">Railway → your service → Variables</strong> and add it, then Railway will restart automatically.
                    </p>
                  </div>
                ) : (
                  <><span className="text-lg flex-shrink-0 text-red-400">❌</span><span className="text-red-400">{error}</span></>
                )}
              </div>
            ) : (
              <>
                {/* Result header */}
                <div className="flex items-center gap-2 mb-5 pb-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  <span className="text-[10px] font-bold tracking-widest uppercase text-orange-400">💡 AI Analysis</span>
                  {isCached && (
                    <span className="stat-badge stat-badge-gold">⚡ cached</span>
                  )}
                  <span className="ml-auto text-xs text-slate-600 font-mono">{(elapsed / 1000).toFixed(1)}s</span>
                </div>
                {/* Markdown content */}
                <div className="prose-cricket">
                  <ReactMarkdown>
                    {isCached ? answer!.replace(/^⚡ \*\(cached\)\*\n\n/, '') : answer!}
                  </ReactMarkdown>
                </div>
                {/* Footer actions */}
                <div className="flex items-center justify-end gap-2 mt-5 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                  <button className="btn-ghost" onClick={() => { setAnswer(null); setError(null); }}>
                    ↩ Clear
                  </button>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
