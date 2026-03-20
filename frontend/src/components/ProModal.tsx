/**
 * ProModal — Full-screen upgrade modal with Stripe CTA.
 * Usage: <ProModal open={open} onClose={() => setOpen(false)} />
 */
interface Props {
  open: boolean
  onClose: () => void
}

const FEATURES_FREE = [
  { label: '15 AI questions / day', ok: true },
  { label: 'Player stats & charts', ok: true },
  { label: 'Basic match predictions', ok: true },
  { label: 'Unlimited AI questions', ok: false },
  { label: 'Priority Gemini Pro responses', ok: false },
  { label: 'Export answers to PDF/CSV', ok: false },
  { label: 'No ads ever', ok: false },
  { label: 'Fantasy XI history & saves', ok: false },
]

const FEATURES_PRO = [
  { label: 'Unlimited AI questions', ok: true },
  { label: 'Priority Gemini Pro responses', ok: true },
  { label: 'Export answers to PDF/CSV', ok: true },
  { label: 'No ads ever', ok: true },
  { label: 'Fantasy XI history & saves', ok: true },
  { label: 'Player stats & charts', ok: true },
  { label: 'Basic match predictions', ok: true },
  { label: 'Early access to new features', ok: true },
]

// 👉 Replace this with your real Stripe payment link
const STRIPE_LINK = 'https://buy.stripe.com/your-link'

export default function ProModal({ open, onClose }: Props) {
  if (!open) return null

  const handleUpgrade = () => {
    // If Stripe link is placeholder, show alert
    if (STRIPE_LINK.includes('your-link')) {
      alert('💳 Stripe not yet configured — coming soon!\n\nThe payment system will be live shortly.')
      return
    }
    window.open(STRIPE_LINK, '_blank', 'noopener,noreferrer')
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(12px)' }}
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl rounded-3xl overflow-hidden"
        style={{
          background: 'linear-gradient(145deg, #0d0f1a, #111420)',
          border: '1px solid rgba(255,107,53,0.25)',
          boxShadow: '0 40px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,107,53,0.1)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Gradient top bar */}
        <div className="h-1 w-full" style={{ background: 'linear-gradient(90deg, #ff6b35, #f5c842, #ff6b35)' }} />

        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-xl text-slate-500 hover:text-slate-300 transition-colors"
          style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          ✕
        </button>

        <div className="p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 mb-3 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest"
              style={{ background: 'rgba(255,107,53,0.12)', border: '1px solid rgba(255,107,53,0.25)', color: '#ff6b35' }}>
              ⚡ Upgrade to Pro
            </div>
            <h2 className="text-3xl font-bold text-white mb-2" style={{ fontFamily: '"Playfair Display", serif' }}>
              Unlimited Cricket Intelligence
            </h2>
            <p className="text-slate-400 text-sm max-w-sm mx-auto">
              Remove daily limits and unlock the full power of AI cricket analysis.
            </p>
          </div>

          {/* Plan comparison */}
          <div className="grid grid-cols-2 gap-4 mb-8">
            {/* Free */}
            <div className="rounded-2xl p-5" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <div className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-1">Free</div>
              <div className="text-2xl font-bold text-white mb-4">$0</div>
              <ul className="space-y-2.5">
                {FEATURES_FREE.map(f => (
                  <li key={f.label} className={`flex items-center gap-2 text-xs ${f.ok ? 'text-slate-300' : 'text-slate-600 line-through'}`}>
                    <span className={`flex-shrink-0 text-[10px] ${f.ok ? 'text-green-400' : 'text-slate-700'}`}>
                      {f.ok ? '✓' : '✕'}
                    </span>
                    {f.label}
                  </li>
                ))}
              </ul>
            </div>

            {/* Pro */}
            <div className="rounded-2xl p-5 relative overflow-hidden"
              style={{
                background: 'linear-gradient(145deg, rgba(255,107,53,0.1), rgba(245,200,66,0.06))',
                border: '1px solid rgba(255,107,53,0.3)',
              }}>
              <div className="absolute top-3 right-3">
                <span className="text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(255,107,53,0.2)', color: '#ff6b35', border: '1px solid rgba(255,107,53,0.3)' }}>
                  Popular
                </span>
              </div>
              <div className="text-xs font-bold uppercase tracking-widest text-orange-400 mb-1">Pro</div>
              <div className="text-2xl font-bold text-white mb-4">
                $4.99 <span className="text-sm text-slate-400 font-normal">/mo</span>
              </div>
              <ul className="space-y-2.5">
                {FEATURES_PRO.map(f => (
                  <li key={f.label} className="flex items-center gap-2 text-xs text-slate-300">
                    <span className="flex-shrink-0 text-[10px] text-green-400">✓</span>
                    {f.label}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* CTA */}
          <button
            onClick={handleUpgrade}
            className="w-full py-4 rounded-2xl text-sm font-bold text-white transition-all duration-200 hover:opacity-90 active:scale-95"
            style={{
              background: 'linear-gradient(135deg, #ff6b35, #f5c842)',
              boxShadow: '0 8px 24px rgba(255,107,53,0.35)',
            }}
          >
            Upgrade to Pro ✦ — $4.99/mo
          </button>
          <p className="text-center text-[10px] text-slate-600 mt-3">
            Cancel anytime · No commitments · Secure payment via Stripe
          </p>
        </div>
      </div>
    </div>
  )
}
