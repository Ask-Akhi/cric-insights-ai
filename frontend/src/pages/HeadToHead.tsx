import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { callAsk, callH2H, callTeamSearch, H2HData } from '../lib/api'
import GenericSearchInput from '../components/GenericSearchInput'
import ReactMarkdown from 'react-markdown'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function HeadToHead({ apiBase, format, grounded }: Props) {
  const [teamA, setTeamA]       = useState('')
  const [teamB, setTeamB]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [aiLoading, setAiLoad]  = useState(false)
  const [data, setData]         = useState<H2HData | null>(null)
  const [aiAnswer, setAiAnswer] = useState<string | null>(null)
  const [error, setError]       = useState<string | null>(null)
  const [tab, setTab]           = useState<'data' | 'ai'>('data')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!teamA.trim() || !teamB.trim()) return
    setError(null); setData(null); setAiAnswer(null)
    setLoading(true); setAiLoad(true)

    callH2H(apiBase, teamA.trim(), teamB.trim(), format)
      .then(setData)
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false))

    callAsk(apiBase, {
      prompt: `Head-to-head analysis between ${teamA} and ${teamB} in ${format} cricket. Include: overall win-loss record, record in last 10 meetings, home/away breakdown, key player matchups, current form of both teams, and a match prediction with reasoning.`,
      context: { format, team_a: teamA, team_b: teamB },
      grounded,
    })
      .then(r => setAiAnswer(r.answer))
      .catch(() => setAiAnswer(null))
      .finally(() => setAiLoad(false))
  }

  const winsTotal = (data?.wins_a ?? 0) + (data?.wins_b ?? 0)
  const winPctA   = winsTotal > 0 ? Math.round(((data?.wins_a ?? 0) / winsTotal) * 100) : 50
  const winPctB   = 100 - winPctA

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl flex-shrink-0 animate-float"
          style={{ background: 'linear-gradient(135deg,rgba(239,68,68,.2),rgba(220,38,38,.08))', border: '1px solid rgba(239,68,68,.25)' }}>
          ⚔️
        </div>
        <div className="pt-1">
          <h2 className="text-2xl font-bold text-white leading-tight" style={{ fontFamily: '"Playfair Display",Georgia,serif' }}>
            Head-to-Head
          </h2>
          <p className="text-sm text-slate-500 mt-1">Cricsheet historical record + AI matchup analysis</p>
        </div>
      </div>

            {/* Form */}
      <form onSubmit={handleSubmit} className="glass-strong p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <GenericSearchInput
            id="h2h-team-a"
            label="Team A"
            value={teamA}
            onChange={setTeamA}
            onSearch={q => callTeamSearch(apiBase, q)}
            placeholder="e.g. India"
            icon="🏏"
          />
          <GenericSearchInput
            id="h2h-team-b"
            label="Team B"
            value={teamB}
            onChange={setTeamB}
            onSearch={q => callTeamSearch(apiBase, q)}
            placeholder="e.g. Australia"
            icon="🏏"
          />
        </div>
        <button type="submit" disabled={loading || aiLoading || !teamA.trim() || !teamB.trim()} className="btn-primary w-full">
          {loading || aiLoading ? <><span className="animate-spin mr-2">⏳</span>Analysing…</> : '⚔️ Compare Teams'}
        </button>
      </form>

      {error && <div className="glass p-4 text-sm text-red-400 border border-red-500/20 rounded-xl">{error}</div>}

      <AnimatePresence>
        {(data || aiAnswer) && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-5">
            {/* Tabs */}
            <div className="flex gap-2 p-1 rounded-xl w-fit" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <button onClick={() => setTab('data')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'data' ? 'bg-red-500 text-white' : 'text-slate-400'}`}>
                📊 Cricsheet Data
              </button>
              <button onClick={() => setTab('ai')} className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${tab === 'ai' ? 'bg-orange-500 text-white' : 'text-slate-400'}`}>
                💬 AI Analysis {aiLoading ? '⏳' : ''}
              </button>
            </div>

            {/* DATA TAB */}
            {tab === 'data' && (
              <div className="space-y-4">
                {loading && <div className="glass p-6 space-y-3"><div className="shimmer-line h-4 w-1/2" /><div className="shimmer-line h-3 w-full" /></div>}
                {data && !loading && (
                  data.found ? (
                    <>
                      {/* Win bar */}
                      <div className="glass p-5 space-y-4">
                        <div className="flex items-center justify-between text-sm">
                          <span className="font-bold text-blue-400">{teamA}</span>
                          <span className="text-slate-500 text-xs">{data.matches} matches played</span>
                          <span className="font-bold text-red-400">{teamB}</span>
                        </div>
                        <div className="flex h-4 rounded-full overflow-hidden">
                          <div className="bg-blue-500 transition-all" style={{ width: `${winPctA}%` }} />
                          <div className="bg-red-500 transition-all" style={{ width: `${winPctB}%` }} />
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-blue-400 font-bold text-lg">{data.wins_a} <span className="text-xs text-slate-500 font-normal">wins</span></span>
                          <span className="text-slate-600 text-xs">{(data.matches ?? 0) - (data.wins_a ?? 0) - (data.wins_b ?? 0)} no result</span>
                          <span className="text-red-400 font-bold text-lg">{data.wins_b} <span className="text-xs text-slate-500 font-normal">wins</span></span>
                        </div>
                      </div>                      {/* Top batters */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {data.top_batters_a && data.top_batters_a.length > 0 && (
                          <div className="glass p-5 space-y-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-blue-400">🏏 {teamA} Top Batters</p>
                            {data.top_batters_a.map((b, i) => (
                              <div key={b.batter} className="flex items-center gap-3">
                                <span className="text-[10px] font-bold text-slate-600 w-4">{i + 1}</span>
                                <span className="text-sm text-slate-200 flex-1 truncate">{b.batter}</span>
                                <span className="text-sm font-bold text-blue-400">{b.runs}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {data.top_batters_b && data.top_batters_b.length > 0 && (
                          <div className="glass p-5 space-y-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-red-400">🏏 {teamB} Top Batters</p>
                            {data.top_batters_b.map((b, i) => (
                              <div key={b.batter} className="flex items-center gap-3">
                                <span className="text-[10px] font-bold text-slate-600 w-4">{i + 1}</span>
                                <span className="text-sm text-slate-200 flex-1 truncate">{b.batter}</span>
                                <span className="text-sm font-bold text-red-400">{b.runs}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Top bowlers */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {data.top_bowlers_a && data.top_bowlers_a.length > 0 && (
                          <div className="glass p-5 space-y-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-blue-400">🎳 {teamA} Top Bowlers</p>
                            {data.top_bowlers_a.map((b, i) => (
                              <div key={b.bowler} className="flex items-center gap-3">
                                <span className="text-[10px] font-bold text-slate-600 w-4">{i + 1}</span>
                                <span className="text-sm text-slate-200 flex-1 truncate">{b.bowler}</span>
                                <span className="text-sm font-bold text-amber-400">{b.wickets}w</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {data.top_bowlers_b && data.top_bowlers_b.length > 0 && (
                          <div className="glass p-5 space-y-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-red-400">🎳 {teamB} Top Bowlers</p>
                            {data.top_bowlers_b.map((b, i) => (
                              <div key={b.bowler} className="flex items-center gap-3">
                                <span className="text-[10px] font-bold text-slate-600 w-4">{i + 1}</span>
                                <span className="text-sm text-slate-200 flex-1 truncate">{b.bowler}</span>
                                <span className="text-sm font-bold text-amber-400">{b.wickets}w</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="glass p-6 text-sm text-slate-500 text-center">
                      No Cricsheet matches found between "{teamA}" and "{teamB}". Check team name spelling.
                    </div>
                  )
                )}
              </div>
            )}

            {/* AI TAB */}
            {tab === 'ai' && (
              <div className="glass p-6">
                {aiLoading && <div className="space-y-3"><div className="shimmer-line h-4 w-3/4" /><div className="shimmer-line h-4 w-full" /><div className="shimmer-line h-4 w-5/6" /></div>}
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
