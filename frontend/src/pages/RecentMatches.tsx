import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { callRecentMatches, callAsk, callTeamSearch, MatchRow } from '../lib/api'
import GenericSearchInput from '../components/GenericSearchInput'
import ReactMarkdown from 'react-markdown'

interface Props { apiBase: string; format: string; grounded: boolean; onQuestionAsked?: () => void }

function MatchCard({ m }: { m: MatchRow }) {
  const date = m.start_date ? m.start_date.slice(0, 10) : '—'
  return (
    <div className="flex items-start gap-4 px-4 py-3 rounded-xl transition-colors"
      style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
      <div className="flex-shrink-0 text-center">
        <p className="text-[10px] text-slate-600 uppercase tracking-wide">{date}</p>
        <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-[9px] font-bold bg-orange-500/10 text-orange-400 border border-orange-500/20">
          {m.format}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-slate-100 truncate">{m.venue || '—'}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">
          {m.city ? `${m.city} · ` : ''}{m.toss_winner ? `Toss: ${m.toss_winner} (${m.toss_decision})` : ''}
        </p>
      </div>
      {m.winner && (
        <div className="flex-shrink-0 text-right">
          <p className="text-[10px] text-slate-600 uppercase tracking-wide">Winner</p>
          <p className="text-xs font-bold text-green-400 mt-0.5 truncate max-w-[120px]">{m.winner}</p>
        </div>
      )}
    </div>
  )
}

export default function RecentMatches({ apiBase, format, grounded, onQuestionAsked }: Props) {
  const [team, setTeam]         = useState('')
  const [n, setN]               = useState(10)
  const [loading, setLoading]   = useState(false)
  const [aiLoading, setAiLoad]  = useState(false)
  const [matches, setMatches]   = useState<MatchRow[] | null>(null)
  const [aiAnswer, setAiAnswer] = useState<string | null>(null)
  const [error, setError]       = useState<string | null>(null)
  const [tab, setTab]           = useState<'data' | 'ai'>('data')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null); setMatches(null); setAiAnswer(null)
    setLoading(true); setAiLoad(true)

    callRecentMatches(apiBase, format, team.trim() || undefined, n)
      .then(rows => setMatches(rows.slice(0, n)))
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false))

    callAsk(apiBase, {
      prompt: `List and analyse the last ${n} ${format} matches${team ? ` for ${team}` : ''}. For each match include: date, opposition, venue, result, key scores, and standout performers. End with a current form summary and trend.`,
      context: { format, team, n },
      grounded,
    })
      .then(r => { setAiAnswer(r.answer); onQuestionAsked?.() })
      .catch(() => setAiAnswer(null))
      .finally(() => setAiLoad(false))
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl flex-shrink-0 animate-float"
          style={{ background: 'linear-gradient(135deg,rgba(16,185,129,.2),rgba(5,150,105,.08))', border: '1px solid rgba(16,185,129,.25)' }}>
          📅
        </div>
        <div className="pt-1">
          <h2 className="text-2xl font-bold text-white leading-tight" style={{ fontFamily: '"Playfair Display",Georgia,serif' }}>
            Recent Matches
          </h2>
          <p className="text-sm text-slate-500 mt-1">Recent match log + AI form analysis</p>
        </div>
      </div>

            {/* Form */}
      <form onSubmit={handleSubmit} className="glass-strong p-6 space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-2">
            <GenericSearchInput
              id="recent-team"
              label="Team Name (optional)"
              value={team}
              onChange={setTeam}
              onSearch={q => callTeamSearch(apiBase, q)}
              placeholder="e.g. Mumbai Indians (or leave blank for all)"
              icon="🏏"
            />
          </div>
          <div>
            <label className="field-label">No. of Matches</label>
            <input type="number" min={1} max={50} className="input" value={n} onChange={e => setN(Number(e.target.value))} />
          </div>
        </div>
        <button type="submit" disabled={loading || aiLoading} className="btn-primary w-full">
          {loading || aiLoading ? <><span className="animate-spin mr-2">⏳</span>Loading…</> : '📅 Fetch Matches'}
        </button>
      </form>

      {error && <div className="glass p-4 text-sm text-red-400 border border-red-500/20 rounded-xl">{error}</div>}

      <AnimatePresence>
        {(matches !== null || aiAnswer) && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-5">
            {/* Tabs */}
            <div className="flex gap-2 p-1 rounded-xl w-fit" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <button onClick={() => setTab('data')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'data' ? 'bg-green-600 text-white' : 'text-slate-400'}`}>
                📋 Match List
              </button>
              <button onClick={() => setTab('ai')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'ai' ? 'bg-orange-500 text-white' : 'text-slate-400'}`}>
                💬 AI Analysis {aiLoading ? '⏳' : ''}
              </button>
            </div>

            {/* DATA TAB */}
            {tab === 'data' && (
              <div className="space-y-2">
                {loading && <div className="glass p-6 space-y-3"><div className="shimmer-line h-4 w-1/2" /><div className="shimmer-line h-3 w/full" /></div>}
                {!loading && matches && matches.length > 0 && matches.map(m => <MatchCard key={m.match_id} m={m} />)}
                {!loading && matches && matches.length === 0 && (
                  <div className="glass p-6 text-sm text-slate-500 text-center">No matches found for this filter.</div>
                )}
              </div>
            )}

            {/* AI TAB */}
            {tab === 'ai' && (
              <div className="glass p-6">
                {aiLoading && <div className="space-y-3"><div className="shimmer-line h-4 w-3/4" /><div className="shimmer-line h-4 w/full" /></div>}
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
