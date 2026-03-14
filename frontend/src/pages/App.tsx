import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import AskAI from './AskAI'
import BatterStats from './BatterStats'
import BowlerStats from './BowlerStats'
import VenueStats from './VenueStats'
import HeadToHead from './HeadToHead'
import RecentMatches from './RecentMatches'
import MatchInsights from './MatchInsights'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

const TOOLS = [
  { id: 'ask',     icon: '💬', label: 'Ask AI',         desc: 'Cricket Q&A' },
  { id: 'batter',  icon: '🏏', label: 'Batter Stats',   desc: 'Batting analysis' },
  { id: 'bowler',  icon: '🎳', label: 'Bowler Stats',   desc: 'Bowling analysis' },
  { id: 'venue',   icon: '🏟️', label: 'Venue Stats',    desc: 'Ground records' },
  { id: 'h2h',     icon: '⚔️', label: 'Head-to-Head',  desc: 'Team history' },
  { id: 'recent',  icon: '📅', label: 'Recent Matches', desc: 'Latest results' },
  { id: 'insight', icon: '🎯', label: 'Match Insights', desc: 'Pre-match report' },
]

const STATS = [
  { value: '120K+', label: 'Matches Analysed', icon: '🏏' },
  { value: '18K+',  label: 'Players Tracked',  icon: '👤' },
  { value: '50+',   label: 'Venues Covered',   icon: '🏟️' },
  { value: 'Live',  label: 'Web Grounding',    icon: '🌐' },
]

export default function App() {
  const [active, setActive]     = useState('ask')
  const [grounded, setGrounded] = useState(true)
  const [format, setFormat]     = useState('T20')

  const activeTool = TOOLS.find(t => t.id === active)!

  return (
    <div className="min-h-screen app-bg relative overflow-x-hidden">
      {/* Ambient orbs */}
      <div className="orb w-[600px] h-[600px] bg-orange-500 top-[-200px] left-[-200px]" style={{ opacity: 0.10 }} />
      <div className="orb w-[500px] h-[500px] bg-indigo-600 bottom-[-150px] right-[-150px]" style={{ opacity: 0.08 }} />
      <div className="orb w-[300px] h-[300px] bg-amber-400 top-[40%] left-[55%]" style={{ opacity: 0.05 }} />

      {/* ── Top Navigation ───────────────────────────────────── */}
      <header className="relative z-20 border-b border-white/[0.06]" style={{ backdropFilter: 'blur(20px)', background: 'rgba(5,7,15,0.7)' }}>
        <div className="max-w-screen-xl mx-auto px-6 py-4 flex items-center justify-between">

          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 flex items-center justify-center text-xl shadow-lg shadow-orange-500/30 animate-float">
                🏏
              </div>
              <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-green-400 rounded-full border-2 border-[#05070f] animate-pulse" />
            </div>
            <div>
              <h1 className="text-base font-bold text-white tracking-tight leading-none">
                Cric Insights <span className="text-orange-400">AI</span>
              </h1>
              <p className="text-[10px] text-slate-500 mt-0.5 tracking-wide">AI - CricAnalyst</p>
            </div>
          </div>

          {/* Centre nav */}
          <nav className="hidden md:flex items-center gap-1 p-1 rounded-xl" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
            {['T20', 'ODI', 'Test'].map(f => (
              <button key={f} onClick={() => setFormat(f)} className={`nav-pill ${format === f ? 'active' : ''}`}>{f}</button>
            ))}
          </nav>

          {/* Right controls */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setGrounded(g => !g)}
              className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold border transition-all duration-300 ${
                grounded
                  ? 'border-green-500/30 text-green-400 bg-green-500/[0.08]'
                  : 'border-white/10 text-slate-500 bg-white/[0.03]'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${grounded ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
              {grounded ? 'Live' : 'Offline'}
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero Banner ──────────────────────────────────────── */}
      <section className="relative z-10 border-b border-white/[0.05]" style={{ background: 'linear-gradient(180deg, rgba(255,107,53,0.05) 0%, transparent 100%)' }}>
        <div className="max-w-screen-xl mx-auto px-6 py-12 flex flex-col md:flex-row items-center gap-10">

          {/* Editorial headline */}
          <div className="flex-1 animate-slide-up">
            <div className="inline-flex items-center gap-2 mb-4 px-3 py-1.5 rounded-full text-xs font-semibold tracking-widest uppercase"
              style={{ background: 'rgba(255,107,53,0.12)', border: '1px solid rgba(255,107,53,0.25)', color: '#ff6b35' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse" />
              IPL 2026 · Live Analysis
            </div>
            <h2 className="text-4xl md:text-5xl font-bold text-white leading-[1.1] tracking-tight mb-3"
              style={{ fontFamily: '"Playfair Display", Georgia, serif' }}>
              Cricket Intelligence,{' '}
              <span style={{ background: 'linear-gradient(135deg, #ff6b35, #f5c842)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                Reimagined.
              </span>
            </h2>
            <p className="text-slate-400 text-base leading-relaxed max-w-md">
              AI-powered insights for fantasy teams, match predictions, player analysis, and live IPL data — all in one place.
            </p>
          </div>

          {/* Stats ticker */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 flex-shrink-0 w-full md:w-auto animate-fade-in">
            {STATS.map((s, i) => (
              <div key={i} className="ticker-card">
                <div className="text-2xl mb-1">{s.icon}</div>
                <div className="text-xl font-bold text-white" style={{ fontFamily: '"Playfair Display", serif' }}>{s.value}</div>
                <div className="text-[10px] text-slate-500 font-medium tracking-wide uppercase mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Main Layout ──────────────────────────────────────── */}
      <div className="relative z-10 max-w-screen-xl mx-auto px-6 py-8 flex gap-6">

        {/* ── Sidebar ───────────────────────────────────────── */}
        <aside className="w-52 shrink-0 flex flex-col gap-2 sticky top-6 self-start">

          {/* Format (mobile) */}
          <div className="flex md:hidden items-center gap-1 p-1 rounded-xl mb-2" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
            {['T20', 'ODI', 'Test'].map(f => (
              <button key={f} onClick={() => setFormat(f)} className={`nav-pill flex-1 text-center ${format === f ? 'active' : ''}`}>{f}</button>
            ))}
          </div>

          <p className="text-[10px] font-bold text-slate-600 uppercase tracking-[0.12em] px-1 mb-1">Tools</p>

          {TOOLS.map(t => (
            <motion.button
              key={t.id}
              onClick={() => setActive(t.id)}
              whileTap={{ scale: 0.97 }}
              className={`tool-card ${active === t.id ? 'active' : ''}`}
            >
              <span className="tool-icon">{t.icon}</span>
              <span className="flex flex-col items-start min-w-0">
                <span className={`text-xs font-semibold leading-none ${active === t.id ? 'text-orange-400' : 'text-slate-200'}`}>{t.label}</span>
                <span className="text-[10px] text-slate-600 mt-1 leading-none">{t.desc}</span>
              </span>
            </motion.button>
          ))}

          {/* Status panel */}
          <div className="mt-4 glass p-4 space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse flex-shrink-0" />
              <span className="text-xs text-slate-300 font-medium">System Online</span>
            </div>
            <div className="section-divider" />
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-600 uppercase tracking-wide">Format</span>
                <span className="stat-badge stat-badge-orange">{format}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-600 uppercase tracking-wide">Search</span>
                <span className={`stat-badge ${grounded ? 'stat-badge-green' : 'stat-badge-blue'}`}>
                  {grounded ? 'Live' : 'Offline'}
                </span>
              </div>
            </div>
          </div>
        </aside>

        {/* ── Main Content ──────────────────────────────────── */}
        <main className="flex-1 min-w-0">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 mb-6">
            <span className="text-slate-600 text-xs">Tools</span>
            <span className="text-slate-700 text-xs">/</span>
            <span className="text-orange-400 text-xs font-semibold">{activeTool.label}</span>
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 20, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.98 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              {active === 'ask'     && <AskAI        apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'batter'  && <BatterStats   apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'bowler'  && <BowlerStats   apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'venue'   && <VenueStats    apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'h2h'     && <HeadToHead    apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'recent'  && <RecentMatches apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'insight' && <MatchInsights apiBase={API_BASE} format={format} grounded={grounded} />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* ── Footer ───────────────────────────────────────────── */}
      <footer className="relative z-10 mt-16 border-t border-white/[0.05]" style={{ background: 'rgba(5,7,15,0.6)' }}>
        <div className="max-w-screen-xl mx-auto px-6 py-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-orange-500">🏏</span>
            <span className="text-sm font-semibold text-slate-300">Cric Insights AI</span>
            <span className="text-slate-700 text-sm">·</span>
            <span className="text-xs text-slate-600">AI - CricAnalyst</span>
          </div>
          <div className="flex items-center gap-4 text-[11px] text-slate-700">
            <span>Powered by AI · Cricsheet Data</span>
            <span>·</span>
            <span>© 2026</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
