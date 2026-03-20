import { useState } from 'react'
import ProModal from './ProModal'

/**
 * ProBanner — Monetisation component.
 *
 * Renders in two modes:
 *  - "inline"  → compact upgrade card inside tool panels (e.g. below Fantasy AI result)
 *  - "sidebar" → persistent mini panel in the sidebar
 *
 * HOW TO ENABLE REAL PAYMENTS (when ready):
 *  1. Create a Stripe account → get a Payment Link URL for a "Pro" product ($4.99/mo)
 *  2. Replace STRIPE_LINK with that URL
 *  3. On payment, Stripe Webhook → your backend sets user.is_pro = true
 *  4. Pass `isPro` prop from auth context → hides banner for paying users
 *
 * For now it's a pure UI teaser — no Stripe integration yet.
 */

interface InlineProps {
  variant: 'inline'
  feature: string        // e.g. "Unlimited Fantasy AI picks"
  description?: string
}

interface SidebarProps {
  variant: 'sidebar'
  questionsLeft?: number // free tier questions remaining today
}

type Props = InlineProps | SidebarProps

// Stripe payment link — replace with real one when ready
const STRIPE_LINK = '#'   // e.g. 'https://buy.stripe.com/your-link'
const PRO_PRICE   = '$4.99/mo'

export default function ProBanner(props: Props) {
  const [modalOpen, setModalOpen] = useState(false)

  if (props.variant === 'sidebar') {
    const left = props.questionsLeft ?? 10
    const pct  = Math.max(0, Math.min(100, (left / 15) * 100))
    return (
      <>
        <ProModal open={modalOpen} onClose={() => setModalOpen(false)} />
        <div
          className="rounded-2xl p-4 space-y-3"
          style={{
            background: 'linear-gradient(135deg, rgba(255,107,53,0.08), rgba(245,200,66,0.06))',
            border: '1px solid rgba(255,107,53,0.2)',
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-widest text-orange-400">⚡ Pro Plan</span>
            <span className="text-[10px] font-bold text-amber-400">{PRO_PRICE}</span>
          </div>

          {/* Usage bar */}
          <div className="space-y-1">
            <div className="flex justify-between text-[10px] text-slate-500">
              <span>Daily AI questions</span>
              <span className={left <= 3 ? 'text-red-400 font-bold' : 'text-slate-400'}>{left} left</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${pct}%`,
                  background: left <= 3
                    ? 'linear-gradient(90deg, #ef4444, #f97316)'
                    : 'linear-gradient(90deg, #ff6b35, #f5c842)',
                }}
              />
            </div>
          </div>

          {/* Features */}
          <ul className="space-y-1.5">
            {['Unlimited AI questions', 'Priority LLM responses', 'Export to PDF/CSV', 'No ads ever'].map(f => (
              <li key={f} className="flex items-center gap-1.5 text-[10px] text-slate-400">
                <span className="text-green-400 flex-shrink-0">✓</span>{f}
              </li>
            ))}
          </ul>

          {/* CTA */}
          <button
            onClick={() => setModalOpen(true)}
            className="block w-full text-center py-2 rounded-xl text-xs font-bold text-white transition-all duration-200 hover:opacity-90 active:scale-95"
            style={{ background: 'linear-gradient(135deg, #ff6b35, #f5c842)', boxShadow: '0 4px 12px rgba(255,107,53,0.3)' }}
          >
            Upgrade to Pro ✦
          </button>
          <p className="text-[9px] text-slate-700 text-center">Cancel anytime · No commitments</p>
        </div>
      </>
    )
  }

  // inline variant
  return (
    <>
      <ProModal open={modalOpen} onClose={() => setModalOpen(false)} />
      <div
        className="flex items-center gap-4 p-4 rounded-2xl mt-4"
        style={{
          background: 'linear-gradient(135deg, rgba(255,107,53,0.06), rgba(245,200,66,0.04))',
          border: '1px solid rgba(255,107,53,0.15)',
        }}
      >
        <div className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-xl"
          style={{ background: 'rgba(255,107,53,0.12)', border: '1px solid rgba(255,107,53,0.2)' }}>
          ⚡
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold text-white">{props.feature}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">
            {props.description ?? 'Available on Pro — unlimited AI analysis, no daily limits.'}
          </p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="flex-shrink-0 px-3 py-1.5 rounded-xl text-xs font-bold text-white transition-all hover:opacity-90"
          style={{ background: 'linear-gradient(135deg, #ff6b35, #f5c842)' }}
        >
          Go Pro
        </button>
      </div>
    </>
  )
}
