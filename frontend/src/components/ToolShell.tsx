import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'

interface Props {
  icon: string
  title: string
  subtitle?: string
  onSubmit: () => Promise<string>
  children: React.ReactNode   // form fields
}

export default function ToolShell({ icon, title, subtitle, onSubmit, children }: Props) {
  const [loading, setLoading]   = useState(false)
  const [answer, setAnswer]     = useState<string | null>(null)
  const [error, setError]       = useState<string | null>(null)
  const [elapsed, setElapsed]   = useState<number>(0)
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
    } catch (err: any) {
      setError(String(err))
    } finally {
      setLoading(false)
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }

  const isCached = answer?.startsWith('⚡')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-14 h-14 rounded-2xl glass flex items-center justify-center text-3xl animate-float">
          {icon}
        </div>
        <div>
          <h2 className="text-2xl font-bold text-white">{title}</h2>
          {subtitle && <p className="text-sm text-slate-400">{subtitle}</p>}
        </div>
      </div>

      {/* Form card */}
      <form onSubmit={handleSubmit} className="glass p-6 space-y-4">
        {children}
        <button
          type="submit"
          disabled={loading}
          className="btn-primary w-full justify-center disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <>
              <Spinner />
              Analysing… {(elapsed / 1000).toFixed(1)}s
            </>
          ) : (
            <>{icon} Analyse</>
          )}
        </button>
      </form>

      {/* Result card */}
      <AnimatePresence>
        {(answer || error) && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="glass p-6"
          >
            {error ? (
              <div className="text-red-400 text-sm">{error}</div>
            ) : (
              <>
                <div className="flex items-center gap-2 mb-4 pb-4 border-b border-white/10">
                  <span className="text-orange-400 font-semibold text-sm">💡 AI Analysis</span>
                  {isCached && (
                    <span className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
                      ⚡ cached
                    </span>
                  )}
                  <span className="ml-auto text-xs text-slate-500">{(elapsed / 1000).toFixed(1)}s</span>
                </div>
                <div className="prose-cricket">
                  <ReactMarkdown>{isCached ? answer!.replace(/^⚡ \*\(cached\)\*\n\n/, '') : answer!}</ReactMarkdown>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  )
}
