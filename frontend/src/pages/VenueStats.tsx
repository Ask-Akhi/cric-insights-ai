import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { callAsk, callVenueStats, callVenueSearch, VenueStatsData } from '../lib/api'
import GenericSearchInput from '../components/GenericSearchInput'
import ReactMarkdown from 'react-markdown'

interface Props { apiBase: string; format: string; grounded: boolean }

function StatBox({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="glass p-4 rounded-xl text-center">
      <p className="text-2xl font-bold text-white">{value ?? '—'}</p>
      <p className="text-[10px] text-slate-500 uppercase tracking-widest mt-1">{label}</p>
    </div>
  )
}

export default function VenueStats({ apiBase, format, grounded }: Props) {
  const [venue, setVenue]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [aiLoading, setAiLoad]  = useState(false)
  const [stats, setStats]       = useState<VenueStatsData | null>(null)
  const [aiAnswer, setAiAnswer] = useState<string | null>(null)
  const [error, setError]       = useState<string | null>(null)
  const [tab, setTab]           = useState<'data' | 'ai'>('data')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!venue.trim()) return
    setError(null); setStats(null); setAiAnswer(null)
    setLoading(true); setAiLoad(true)

    callVenueStats(apiBase, venue.trim(), format)
      .then(setStats)
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false))

    callAsk(apiBase, {
      prompt: `Detailed venue analysis for ${venue} in ${format} cricket. Include: average first innings score, average second innings score, pitch nature (batting/bowling/balanced), typical conditions, highest team scores, records at this ground, and advice for teams batting first vs second.`,
      context: { format, venue },
      grounded,
    })
      .then(setAiAnswer)
      .catch(() => setAiAnswer(null))
      .finally(() => setAiLoad(false))
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl flex-shrink-0 animate-float"
          style={{ background: 'linear-gradient(135deg,rgba(99,102,241,.2),rgba(79,70,229,.08))', border: '1px solid rgba(99,102,241,.25)' }}>
          🏟️
        </div>
        <div className="pt-1">
          <h2 className="text-2xl font-bold text-white leading-tight" style={{ fontFamily: '"Playfair Display",Georgia,serif' }}>
            Venue Statistics
          </h2>
          <p className="text-sm text-slate-500 mt-1">Cricsheet ball-by-ball ground records + AI analysis</p>
        </div>
      </div>

            {/* Form */}
      <form onSubmit={handleSubmit} className="glass-strong p-6 space-y-4">
        <GenericSearchInput
          id="venue-search"
          label="Venue / Stadium Name"
          value={venue}
          onChange={setVenue}
          onSearch={q => callVenueSearch(apiBase, q)}
          placeholder="e.g. Wankhede Stadium"
          icon="🏟️"
        />
        <button type="submit" disabled={loading || aiLoading || !venue.trim()} className="btn-primary w-full">
          {loading || aiLoading ? <><span className="animate-spin mr-2">⏳</span>Analysing…</> : '🏟️ Get Venue Stats'}
        </button>
      </form>

      {error && <div className="glass p-4 text-sm text-red-400 border border-red-500/20 rounded-xl">{error}</div>}

      <AnimatePresence>
        {(stats || aiAnswer) && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-5">
            {/* Tab bar */}
            <div className="flex gap-2 p-1 rounded-xl w-fit" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <button onClick={() => setTab('data')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'data' ? 'bg-indigo-500 text-white' : 'text-slate-400'}`}>
                📊 Cricsheet Data
              </button>
              <button onClick={() => setTab('ai')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'ai' ? 'bg-orange-500 text-white' : 'text-slate-400'}`}>
                💬 AI Analysis {aiLoading ? '⏳' : ''}
              </button>
            </div>

            {/* DATA TAB */}
            {tab === 'data' && (
              <div className="space-y-4">
                {loading && (
                  <div className="glass p-6 space-y-3">
                    <div className="shimmer-line h-4 w-1/3" /><div className="shimmer-line h-3 w-full" />
                  </div>
                )}
                {stats && !loading && (
                  stats.found ? (
                    <>
                      {/* Key stats */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <StatBox label="Matches" value={stats.matches} />
                        <StatBox label="Avg 1st Innings" value={stats.avg_first_innings_runs != null ? `${stats.avg_first_innings_runs}` : null} />
                        <StatBox label="Avg 2nd Innings" value={stats.avg_second_innings_runs != null ? `${stats.avg_second_innings_runs}` : null} />
                        <StatBox label="Format Filter" value={format} />
                      </div>
                      {/* Top performers */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {stats.top_scorers && stats.top_scorers.length > 0 && (
                          <div className="glass p-5 space-y-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-orange-400">🏏 Top Run Scorers</p>
                            {stats.top_scorers.map((s, i) => (
                              <div key={s.batter} className="flex items-center gap-3">
                                <span className="text-[10px] font-bold text-slate-600 w-4">{i + 1}</span>
                                <span className="text-sm text-slate-200 flex-1 truncate">{s.batter}</span>
                                <span className="text-sm font-bold text-orange-400">{s.runs}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {stats.top_wicket_takers && stats.top_wicket_takers.length > 0 && (
                          <div className="glass p-5 space-y-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-amber-400">🎳 Top Wicket Takers</p>
                            {stats.top_wicket_takers.map((w, i) => (
                              <div key={w.bowler} className="flex items-center gap-3">
                                <span className="text-[10px] font-bold text-slate-600 w-4">{i + 1}</span>
                                <span className="text-sm text-slate-200 flex-1 truncate">{w.bowler}</span>
                                <span className="text-sm font-bold text-amber-400">{w.wickets}w</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="glass p-6 text-sm text-slate-500 text-center">
                      No Cricsheet data found for "{venue}". Try a different venue name.
                    </div>
                  )
                )}
              </div>
            )}

            {/* AI TAB */}
            {tab === 'ai' && (
              <div className="glass p-6">
                {aiLoading && (
                  <div className="space-y-3"><div className="shimmer-line h-4 w-3/4" /><div className="shimmer-line h-4 w-full" /><div className="shimmer-line h-4 w-5/6" /></div>
                )}
                {!aiLoading && aiAnswer && (
                  <div className="prose prose-invert prose-sm max-w-none text-slate-300">
                    <ReactMarkdown>{aiAnswer}</ReactMarkdown>
                  </div>
                )}
                {!aiLoading && !aiAnswer && <p className="text-sm text-slate-500">AI analysis unavailable.</p>}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
