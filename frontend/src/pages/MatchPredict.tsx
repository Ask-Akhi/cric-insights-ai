import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { callAsk, callH2H, callTeamSearch, H2HData } from '../lib/api'
import GenericSearchInput from '../components/GenericSearchInput'
import { SkeletonAIResponse, SkeletonCard } from '../components/Skeleton'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface Props { apiBase: string; format: string; grounded: boolean; onQuestionAsked?: () => void }

const QUICK_MATCHES = [
  { a: 'India', b: 'Australia' },
  { a: 'India', b: 'Pakistan' },
  { a: 'England', b: 'Australia' },
  { a: 'South Africa', b: 'West Indies' },
]

export default function MatchPredict({ apiBase, format, grounded, onQuestionAsked }: Props) {
  const [teamA, setTeamA]         = useState('')
  const [teamB, setTeamB]         = useState('')
  const [venue, setVenue]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [h2hLoading, setH2hLoad] = useState(false)
  const [prediction, setPrediction] = useState<string | null>(null)
  const [h2hData, setH2hData]    = useState<H2HData | null>(null)
  const [error, setError]         = useState<string | null>(null)
  const [latency, setLatency]     = useState<number | null>(null)
  const [cacheHit, setCacheHit]  = useState(false)

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!teamA.trim() || !teamB.trim()) return
    setError(null); setPrediction(null); setH2hData(null); setLatency(null)
    setLoading(true); setH2hLoad(true)

    // Fetch H2H data in parallel
    callH2H(apiBase, teamA.trim(), teamB.trim(), format)
      .then(setH2hData)
      .catch(() => {})
      .finally(() => setH2hLoad(false))

    const prompt = [
      `Predict the winner of ${teamA} vs ${teamB} in ${format} cricket`,
      venue ? `at ${venue}` : '',
      `. Give: (1) predicted winner with confidence %, (2) top 3 key factors deciding the match,`,
      ` (3) player to watch from each side, (4) predicted score range,`,
      ` (5) risk factor. Be specific with stats.`,
    ].filter(Boolean).join(' ')

    try {
      const result = await callAsk(apiBase, {
        prompt,
        context: { format, team_a: teamA, team_b: teamB, ...(venue ? { venue } : {}) },
        grounded,
      })
      setPrediction(result.answer)
      setLatency(result.latency_ms)
      setCacheHit(result.rag_cache_hit)
      onQuestionAsked?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Prediction failed')
    } finally {
      setLoading(false)
    }
  }

  const winPctA = h2hData
    ? Math.round(((h2hData.wins_a ?? 0) / Math.max((h2hData.wins_a ?? 0) + (h2hData.wins_b ?? 0), 1)) * 100)
    : 50

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl flex-shrink-0 animate-float"
          style={{ background: 'linear-gradient(135deg,rgba(168,85,247,.2),rgba(139,92,246,.08))', border: '1px solid rgba(168,85,247,.25)' }}>
          🔮
        </div>
        <div className="pt-1">
          <h2 className="text-2xl font-bold text-white leading-tight" style={{ fontFamily: '"Playfair Display",Georgia,serif' }}>
            Match Prediction
          </h2>
          <p className="text-sm text-slate-500 mt-1">AI-powered winner prediction with confidence % and key factors</p>
        </div>
      </div>

      {/* Quick picks */}
      <div className="flex flex-wrap gap-2">
        {QUICK_MATCHES.map(m => (
          <button key={`${m.a}-${m.b}`}
            onClick={() => { setTeamA(m.a); setTeamB(m.b) }}
            className="text-xs px-3 py-1.5 rounded-lg border border-purple-500/20 text-purple-300 hover:bg-purple-500/10 transition-all"
          >
            {m.a} vs {m.b}
          </button>
        ))}
      </div>

      {/* Form */}
      <form onSubmit={handlePredict} className="glass-strong p-5 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <GenericSearchInput id="pred-team-a" label="Team A" value={teamA} onChange={setTeamA}
            onSearch={q => callTeamSearch(apiBase, q)} placeholder="e.g. India" icon="🏏" />
          <GenericSearchInput id="pred-team-b" label="Team B" value={teamB} onChange={setTeamB}
            onSearch={q => callTeamSearch(apiBase, q)} placeholder="e.g. Australia" icon="🏏" />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1.5">Venue (optional)</label>
          <input
            value={venue} onChange={e => setVenue(e.target.value)}
            placeholder="e.g. Wankhede Stadium, Mumbai"
            className="w-full px-3 py-2 rounded-xl bg-white/[0.04] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-purple-500/50"
          />
        </div>
        <button type="submit" disabled={loading || !teamA.trim() || !teamB.trim()} className="btn-primary w-full"
          style={{ background: loading ? undefined : 'linear-gradient(135deg,#7c3aed,#6d28d9)' }}>
          {loading
            ? <><span className="animate-spin mr-2">⏳</span>Predicting…</>
            : '🔮 Predict Winner'}
        </button>
      </form>

      {error && (
        <div className="glass p-4 text-sm text-red-400 border border-red-500/20 rounded-xl">
          ⚠️ {error}
        </div>
      )}

      <AnimatePresence>
        {(h2hLoading || h2hData || loading || prediction) && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-4">

            {/* H2H summary bar */}
            {h2hLoading ? (
              <SkeletonCard />
            ) : h2hData?.found ? (
              <div className="glass p-4 space-y-3">
                <p className="text-xs text-slate-400 font-medium">
                  Historical Record — {h2hData.matches} matches
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-white font-semibold w-24 truncate">{teamA}</span>
                  <div className="flex-1 h-2 rounded-full overflow-hidden bg-white/[0.06]">
                    <div className="h-full rounded-full bg-gradient-to-r from-orange-500 to-amber-400 transition-all"
                      style={{ width: `${winPctA}%` }} />
                  </div>
                  <span className="text-xs text-white font-semibold w-24 text-right truncate">{teamB}</span>
                </div>
                <div className="flex justify-between text-xs text-slate-400">
                  <span>{h2hData.wins_a} wins ({winPctA}%)</span>
                  <span>{h2hData.wins_b} wins ({100 - winPctA}%)</span>
                </div>
              </div>
            ) : null}

            {/* Prediction */}
            {loading ? (
              <SkeletonAIResponse />
            ) : prediction ? (
              <div className="glass-strong p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold text-purple-400 uppercase tracking-wider">🔮 AI Prediction</span>
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    {cacheHit && <span className="text-amber-400">⚡ cached</span>}
                    {latency !== null && <span>{(latency / 1000).toFixed(1)}s</span>}
                  </div>
                </div>
                <div className="prose-cricket">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{prediction}</ReactMarkdown>
                </div>
              </div>
            ) : null}

          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
