import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import AskAI from './AskAI'
import BatterStats from './BatterStats'
import BowlerStats from './BowlerStats'
import VenueStats from './VenueStats'
import HeadToHead from './HeadToHead'
import RecentMatches from './RecentMatches'
import MatchInsights from './MatchInsights'
import Insights from './Insights'
import PlayerCompare from './PlayerCompare'
import FantasyXI from './FantasyXI'
import LiveScoreTicker from '../components/LiveScoreTicker'
// ProBanner / ProModal disabled until Stripe is configured
// import ProBanner from '../components/ProBanner'
// import ProModal from '../components/ProModal'

// Free tier: 15 AI questions per day tracked in localStorage
const FREE_LIMIT = 15
const TODAY_KEY  = () => `cric_q_${new Date().toISOString().slice(0, 10)}`

function useQuestionCounter() {
  const [used, setUsed] = useState<number>(() => {
    try { return parseInt(localStorage.getItem(TODAY_KEY()) ?? '0', 10) } catch { return 0 }
  })
  const increment = () => {
    const next = used + 1
    try { localStorage.setItem(TODAY_KEY(), String(next)) } catch { /* */ }
    setUsed(next)
  }
  return { used, left: Math.max(0, FREE_LIMIT - used), increment, limitHit: used >= FREE_LIMIT }
}
// absolute Railway URL. VITE_API_URL is set via .env.capacitor at build time.
// In the browser (dev + Railway web), the Vite proxy handles /api → 8002.
const isCapacitor = !!(window as Window & { Capacitor?: unknown }).Capacitor
const API_BASE =
  isCapacitor
    ? (import.meta.env.VITE_API_URL ?? 'https://your-railway-app.up.railway.app')
    : (import.meta.env.VITE_API_URL ?? '')

const TOOLS = [
  { id: 'ask',      icon: '💬', label: 'Ask AI',          desc: 'Cricket Q&A' },
  { id: 'batter',   icon: '🏏', label: 'Batter Stats',    desc: 'Batting analysis' },
  { id: 'bowler',   icon: '🎳', label: 'Bowler Stats',    desc: 'Bowling analysis' },
  { id: 'compare',  icon: '⚖️', label: 'Compare Players', desc: 'Side-by-side stats' },
  { id: 'fantasy',  icon: '🏆', label: 'Fantasy XI',      desc: 'Score & rank squad' },
  { id: 'insights', icon: '📊', label: 'Squad Insights',  desc: 'Cricsheet + AI' },
  { id: 'venue',    icon: '🏟️', label: 'Venue Stats',     desc: 'Ground records' },
  { id: 'h2h',      icon: '⚔️', label: 'Head-to-Head',   desc: 'Team history' },
  { id: 'recent',   icon: '📅', label: 'Recent Matches',  desc: 'Latest results' },
  { id: 'insight',  icon: '🎯', label: 'Match Insights',  desc: 'Pre-match report' },
]

const STATS = [
  { value: '21K+',  label: 'Matches Analysed', icon: '🏏' },
  { value: '18K+',  label: 'Players Tracked',  icon: '👤' },
  { value: '10M+',  label: 'Balls in Dataset', icon: '📊' },
  { value: 'AI',    label: 'Web Search',        icon: '🌐' },
]

const CURRENT_YEAR = new Date().getFullYear()

export default function App() {
  const [active, setActive]         = useState('ask')
  const [grounded, setGrounded]     = useState(true)
  const [format, setFormat]         = useState('T20')
  const [menuOpen, setMenuOpen]     = useState(false)
  const [tickerLive, setTickerLive] = useState(false)
  const [backendOk, setBackendOk]   = useState<boolean | null>(null) // null = checking
  const { left, increment }         = useQuestionCounter()

  // ── Real health check ────────────────────────────────────────
  const checkHealth = useCallback(() => {
    fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(5000) })
      .then(r => setBackendOk(r.ok))
      .catch(() => setBackendOk(false))
  }, [])

  useEffect(() => {
    checkHealth()
    const id = setInterval(checkHealth, 30_000)
    return () => clearInterval(id)
  }, [checkHealth])

  const activeTool = TOOLS.find(t => t.id === active)!

  const selectTool = (id: string) => { setActive(id); setMenuOpen(false) }
  return (
    <div className="min-h-screen app-bg relative overflow-x-hidden">
      {/* Pro upgrade modal — disabled until Stripe is configured */}
      {/* <ProModal open={proOpen} onClose={() => setProOpen(false)} /> */}

      {/* Ambient orbs — reduced on mobile for perf */}
      <div className="orb w-[600px] h-[600px] bg-orange-500 top-[-200px] left-[-200px]" style={{ opacity: 0.10 }} />
      <div className="orb w-[500px] h-[500px] bg-indigo-600 bottom-[-150px] right-[-150px]" style={{ opacity: 0.08 }} />

      {/* ── Top Navigation ───────────────────────────────────── */}
      <header className="relative z-30 border-b border-white/[0.06]" style={{ backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', background: 'rgba(5,7,15,0.85)' }}>
        <div className="max-w-screen-xl mx-auto px-4 py-3 flex items-center justify-between gap-3">

          {/* Logo */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="relative">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 flex items-center justify-center text-lg shadow-lg shadow-orange-500/30">
                🏏
              </div>
              <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-[#05070f]"
                style={{ background: tickerLive ? '#4ade80' : '#334155' }}
                title={tickerLive ? 'Live cricket data' : 'Cricsheet dataset (static)'}
              />
            </div>
            <div>
              <h1 className="text-sm font-bold text-white tracking-tight leading-none">
                Cric Insights <span className="text-orange-400">AI</span>
              </h1>
              <p className="text-[10px] text-slate-500 mt-0.5">AI - CricAnalyst</p>
            </div>
          </div>

          {/* Centre: format pills (desktop) */}
          <nav className="hidden md:flex items-center gap-1 p-1 rounded-xl" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
            {['T20', 'ODI', 'Test'].map(f => (
              <button key={f} onClick={() => setFormat(f)} className={`nav-pill ${format === f ? 'active' : ''}`}>{f}</button>
            ))}
          </nav>          {/* Right: live toggle + question counter + mobile menu button */}
          <div className="flex items-center gap-2">
            {/* Questions left — static pill, no Pro modal yet */}
            <div
              className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold border ${
                left <= 3
                  ? 'border-red-500/30 text-red-400 bg-red-500/[0.08]'
                  : 'border-white/10 text-slate-400 bg-white/[0.03]'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${left <= 3 ? 'bg-red-400 animate-pulse' : 'bg-slate-600'}`} />              {left > 0 ? `${left} free` : '0 left'}
            </div>
            <button
              onClick={() => setGrounded(g => !g)}
              title={grounded ? 'Gemini web search ON — AI can look up current info' : 'Web search OFF — AI uses local data only'}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold border transition-all duration-300 ${
                grounded ? 'border-green-500/30 text-green-400 bg-green-500/[0.08]' : 'border-white/10 text-slate-500 bg-white/[0.03]'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${grounded ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
              <span className="hidden sm:inline">{grounded ? 'Web Search' : 'AI Only'}</span>
            </button>
            {/* Mobile hamburger */}
            <button
              className="md:hidden w-9 h-9 flex flex-col items-center justify-center gap-1.5 rounded-xl border border-white/10"
              style={{ background: 'rgba(255,255,255,0.04)' }}
              onClick={() => setMenuOpen(o => !o)}
            >
              <span className={`w-4 h-0.5 bg-slate-300 transition-all duration-200 ${menuOpen ? 'rotate-45 translate-y-2' : ''}`} />
              <span className={`w-4 h-0.5 bg-slate-300 transition-all duration-200 ${menuOpen ? 'opacity-0' : ''}`} />
              <span className={`w-4 h-0.5 bg-slate-300 transition-all duration-200 ${menuOpen ? '-rotate-45 -translate-y-2' : ''}`} />
            </button>
          </div>
        </div>

        {/* Mobile format pills */}
        <div className="md:hidden flex items-center gap-1 px-4 pb-2">
          {['T20', 'ODI', 'Test'].map(f => (            <button key={f} onClick={() => setFormat(f)} className={`nav-pill flex-1 text-center ${format === f ? 'active' : ''}`}>{f}</button>
          ))}
        </div>
      </header>

      {/* ── Live Score Ticker ─────────────────────────────────── */}
      <LiveScoreTicker apiBase={API_BASE} format={format} onLiveChange={setTickerLive} />

      {/* ── Mobile slide-down menu ────────────────────────────── */}
      {menuOpen && (
        <div className="md:hidden fixed inset-0 z-20 pt-24" style={{ background: 'rgba(5,7,15,0.97)' }}
          onClick={() => setMenuOpen(false)}>
          <div className="px-4 py-2 grid grid-cols-2 gap-2 overflow-y-auto max-h-[80vh]" onClick={e => e.stopPropagation()}>
            {TOOLS.map(t => (
              <button
                key={t.id}
                onClick={() => selectTool(t.id)}
                className={`tool-card ${active === t.id ? 'active' : ''}`}
              >
                <span className="tool-icon">{t.icon}</span>
                <span className="flex flex-col items-start min-w-0">
                  <span className={`text-xs font-semibold leading-none ${active === t.id ? 'text-orange-400' : 'text-slate-200'}`}>{t.label}</span>
                  <span className="text-[10px] text-slate-600 mt-1 leading-none">{t.desc}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}      {/* ── Hero Banner ───────────────────────────────────── */}
      <section className="relative z-10 border-b border-white/[0.05]" style={{ background: 'linear-gradient(180deg, rgba(255,107,53,0.06) 0%, transparent 100%)' }}>
        <div className="max-w-screen-xl mx-auto px-4 pt-8 pb-7 md:pt-14 md:pb-12">
          {/* Editorial headline */}
          <div className="animate-slide-up">
            <div className="inline-flex items-center gap-2 mb-4 px-3 py-1 rounded-full text-xs font-semibold tracking-widest uppercase"
              style={{ background: 'rgba(255,107,53,0.12)', border: '1px solid rgba(255,107,53,0.25)', color: '#ff6b35' }}>              <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse" />
              IPL {CURRENT_YEAR} · AI Insights
            </div>
            <h2 className="text-3xl md:text-5xl font-bold text-white leading-[1.1] tracking-tight mb-3"
              style={{ fontFamily: '"Playfair Display", Georgia, serif' }}>
              Cricket Intelligence,{' '}
              <span style={{ background: 'linear-gradient(135deg, #ff6b35, #f5c842)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                Reimagined.
              </span>
            </h2>
            <p className="text-slate-400 text-sm leading-relaxed max-w-md">
              AI-powered insights for fantasy teams, match predictions,{' '}
              <span className="hidden sm:inline">player analysis, and live IPL data — </span>
              all in one place.
            </p>
          </div>
        </div>        {/* Stats strip — full width below the headline */}
        <div className="border-t border-white/[0.05]" style={{ background: 'rgba(255,255,255,0.02)' }}>
          <div className="max-w-screen-xl mx-auto px-4 py-3 md:py-4 grid grid-cols-4 gap-0 animate-fade-in">
            {STATS.map((s, i) => (
              <div key={i} className={`flex items-center gap-2 md:gap-3 min-w-0 py-1 px-3 md:px-5 ${i > 0 ? 'border-l border-white/[0.05]' : ''}`}>
                <span className="text-base md:text-xl flex-shrink-0 opacity-80">{s.icon}</span>
                <div className="min-w-0">
                  <div className="text-xs md:text-sm font-bold text-white leading-none" style={{ fontFamily: '"Playfair Display", serif' }}>{s.value}</div>
                  <div className="text-[9px] md:text-[10px] text-slate-500 font-medium tracking-wide uppercase mt-0.5 truncate">{s.label}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Main Layout ──────────────────────────────────────── */}
      <div className="relative z-10 max-w-screen-xl mx-auto px-3 md:px-6 py-5 md:py-8 flex gap-5">

        {/* ── Sidebar — desktop only ────────────────────────── */}
        <aside className="hidden md:flex w-52 shrink-0 flex-col gap-2 sticky top-6 self-start max-h-[calc(100vh-6rem)] overflow-y-auto">
          <p className="text-[10px] font-bold text-slate-600 uppercase tracking-[0.12em] px-1 mb-1">Tools</p>
          {TOOLS.map(t => (
            <motion.button
              key={t.id}
              onClick={() => selectTool(t.id)}
              whileTap={{ scale: 0.97 }}
              className={`tool-card ${active === t.id ? 'active' : ''}`}
            >
              <span className="tool-icon">{t.icon}</span>
              <span className="flex flex-col items-start min-w-0">
                <span className={`text-xs font-semibold leading-none ${active === t.id ? 'text-orange-400' : 'text-slate-200'}`}>{t.label}</span>
                <span className="text-[10px] text-slate-600 mt-1 leading-none">{t.desc}</span>
              </span>
            </motion.button>
          ))}          {/* Status panel */}
          <div className="mt-4 glass p-4 space-y-3">
            <div className="flex items-center gap-2">
              {backendOk === null ? (
                <span className="w-2 h-2 rounded-full bg-slate-500 animate-pulse flex-shrink-0" />
              ) : backendOk ? (
                <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse flex-shrink-0" />
              ) : (
                <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse flex-shrink-0" />
              )}
              <span className="text-xs text-slate-300 font-medium">
                {backendOk === null ? 'Checking…' : backendOk ? 'System Online' : 'Backend Offline'}
              </span>
              {!backendOk && backendOk !== null && (
                <button onClick={checkHealth} className="ml-auto text-[9px] text-slate-500 hover:text-slate-300 transition-colors">retry</button>
              )}
            </div><div className="section-divider" />
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-600 uppercase tracking-wide">Format</span>
                <span className="stat-badge stat-badge-orange">{format}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-600 uppercase tracking-wide">Search</span>
                <span className={`stat-badge ${grounded ? 'stat-badge-green' : 'stat-badge-blue'}`}>
                  {grounded ? 'Web' : 'AI Only'}
                </span>
              </div>
            </div>
          </div>

          {/* Pro upsell — disabled until Stripe configured */}
          {/* <div className="mt-3"><ProBanner variant="sidebar" questionsLeft={left} /></div> */}
        </aside>

        {/* ── Main Content ──────────────────────────────────── */}
        <main className="flex-1 min-w-0">
          {/* Breadcrumb — mobile shows tool name + hamburger hint */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-slate-600 text-xs hidden md:inline">Tools</span>
            <span className="text-slate-700 text-xs hidden md:inline">/</span>
            <span className="text-orange-400 text-xs font-semibold">{activeTool.icon} {activeTool.label}</span>
            <button className="md:hidden ml-auto text-[10px] text-slate-500 border border-white/10 px-2 py-1 rounded-lg"
              style={{ background: 'rgba(255,255,255,0.04)' }}
              onClick={() => setMenuOpen(true)}>
              ☰ Tools
            </button>
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 20, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.98 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              {active === 'ask'      && <AskAI        apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
              {active === 'batter'   && <BatterStats   apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
              {active === 'bowler'   && <BowlerStats   apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
              {active === 'compare'  && <PlayerCompare apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
              {active === 'fantasy'  && <FantasyXI     apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
              {active === 'insights' && <Insights      apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
              {active === 'venue'    && <VenueStats    apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
              {active === 'h2h'      && <HeadToHead    apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
              {active === 'recent'   && <RecentMatches apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
              {active === 'insight'  && <MatchInsights apiBase={API_BASE} format={format} grounded={grounded} onQuestionAsked={increment} />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>      {/* ── Footer ───────────────────────────────────────────── */}
      <footer className="relative z-10 mt-16 border-t border-white/[0.05]" style={{ background: 'rgba(5,7,15,0.6)' }}>
        <div className="max-w-screen-xl mx-auto px-6 py-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-orange-500">🏏</span>
            <span className="text-sm font-semibold text-slate-300">Cric Insights AI</span>
            <span className="text-slate-700 text-sm">·</span>
            <span className="text-xs text-slate-600">AI - CricAnalyst</span>
          </div>
          <div className="flex items-center flex-wrap justify-center gap-3 text-[11px] text-slate-700">
            <a href="https://cricsheet.org" target="_blank" rel="noopener noreferrer"
              className="hover:text-orange-400 transition-colors">
              📊 Cricsheet Data
            </a>
            <span>·</span>
            <span>Powered by Gemini AI + LangGraph</span>
            <span>·</span>
            <a href="https://github.com/Ask-Akhi/cric-insights-ai" target="_blank" rel="noopener noreferrer"
              className="hover:text-slate-400 transition-colors">
              GitHub
            </a>
            <span>·</span>
            <span>© {CURRENT_YEAR}</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
