import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import AskAI from './AskAI'
import BatterStats from './BatterStats'
import BowlerStats from './BowlerStats'
import VenueStats from './VenueStats'
import HeadToHead from './HeadToHead'
import RecentMatches from './RecentMatches'
import MatchInsights from './MatchInsights'

const API_BASE = 'http://127.0.0.1:8002'

const TOOLS = [
  { id: 'ask',     icon: '💬', label: 'Ask AI',          desc: 'Free-form cricket Q&A' },
  { id: 'batter',  icon: '🏏', label: 'Batter Stats',    desc: 'Career batting analysis' },
  { id: 'bowler',  icon: '🎳', label: 'Bowler Stats',    desc: 'Career bowling analysis' },
  { id: 'venue',   icon: '🏟️', label: 'Venue Stats',     desc: 'Pitch & ground records' },
  { id: 'h2h',     icon: '⚔️', label: 'Head-to-Head',   desc: 'Team vs team history' },
  { id: 'recent',  icon: '📅', label: 'Recent Matches',  desc: 'Last N matches for a team' },
  { id: 'insight', icon: '🎯', label: 'Match Insights',  desc: 'Full pre-match AI report' },
]

export default function App() {
  const [active, setActive] = useState('ask')
  const [grounded, setGrounded] = useState(true)
  const [format, setFormat]   = useState('T20')

  return (
    <div className="min-h-screen gradient-bg relative overflow-hidden">
      {/* Decorative orbs */}
      <div className="orb w-96 h-96 bg-orange-500 top-[-8rem] left-[-8rem]" />
      <div className="orb w-80 h-80 bg-purple-600 bottom-[-6rem] right-[-6rem]" />
      <div className="orb w-64 h-64 bg-blue-600 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />

      {/* Top nav */}
      <header className="relative z-10 border-b border-white/5 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-3xl animate-float inline-block">🏏</span>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">Cric Insights <span className="text-orange-400">AI</span></h1>
              <p className="text-xs text-slate-500">Powered by AI - CricAnalyst</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {/* Format toggle */}
            <div className="flex items-center gap-1 p-1 rounded-xl bg-white/5 border border-white/10">
              {['T20','ODI','Test'].map(f => (
                <button
                  key={f}
                  onClick={() => setFormat(f)}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all duration-200 ${
                    format === f
                      ? 'bg-orange-500 text-white shadow-lg shadow-orange-500/30'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >{f}</button>
              ))}
            </div>
            {/* Live search toggle */}
            <button
              onClick={() => setGrounded(g => !g)}
              className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium border transition-all duration-200 ${
                grounded
                  ? 'bg-green-500/10 border-green-500/40 text-green-400'
                  : 'bg-white/5 border-white/10 text-slate-400'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${grounded ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
              {grounded ? 'Live Search ON' : 'Live Search OFF'}
            </button>
          </div>
        </div>
      </header>

      <div className="relative z-10 max-w-7xl mx-auto px-6 py-8 flex gap-6">
        {/* Sidebar tool list */}
        <aside className="w-56 shrink-0 flex flex-col gap-2">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider px-2 mb-1">Tools</p>
          {TOOLS.map(t => (
            <motion.button
              key={t.id}
              onClick={() => setActive(t.id)}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.97 }}
              className={`tool-card text-left ${active === t.id ? 'active' : ''}`}
            >
              <span className="text-2xl">{t.icon}</span>
              <span className={`text-sm font-semibold ${active === t.id ? 'text-orange-400' : 'text-slate-200'}`}>{t.label}</span>
              <span className="text-xs text-slate-500">{t.desc}</span>
            </motion.button>
          ))}

          {/* Status card */}          <div className="glass p-4 mt-4 space-y-2">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              API Online
            </div>
            <div className="text-xs text-slate-500">Format: <span className="text-orange-400 font-semibold">{format}</span></div>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-w-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              {active === 'ask'     && <AskAI     apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'batter'  && <BatterStats apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'bowler'  && <BowlerStats apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'venue'   && <VenueStats  apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'h2h'     && <HeadToHead  apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'recent'  && <RecentMatches apiBase={API_BASE} format={format} grounded={grounded} />}
              {active === 'insight' && <MatchInsights apiBase={API_BASE} format={format} grounded={grounded} />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/5 mt-8 py-4 text-center text-xs text-slate-600">
        🏏 Cric Insights AI · AI - CricAnalyst · © 2026
      </footer>
    </div>
  )
}
