// Skeleton loading placeholders — replace spinners with content-shaped shimmers.
// Usage: <Skeleton /> for one line, <Skeleton lines={4} /> for a block.

interface SkeletonProps {
  lines?: number
  className?: string
  height?: string
}

export function Skeleton({ lines = 1, className = '', height = 'h-4' }: SkeletonProps) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`${height} rounded-lg bg-white/[0.06] animate-pulse`}
          // Last line slightly shorter for a natural paragraph look
          style={{ width: i === lines - 1 && lines > 1 ? '72%' : '100%' }}
        />
      ))}
    </div>
  )
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`glass p-4 space-y-3 ${className}`}>
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-white/[0.06] animate-pulse flex-shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 rounded bg-white/[0.06] animate-pulse w-2/3" />
          <div className="h-3 rounded bg-white/[0.04] animate-pulse w-1/2" />
        </div>
      </div>
      <Skeleton lines={3} height="h-3" />
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="glass overflow-hidden">
      {/* Header */}
      <div
        className="grid gap-3 px-4 py-3 border-b border-white/[0.06]"
        style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}
      >
        {Array.from({ length: cols }).map((_, i) => (
          <div key={i} className="h-3 rounded bg-white/[0.10] animate-pulse" />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={r}
          className="grid gap-3 px-4 py-3 border-b border-white/[0.04] last:border-0"
          style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}
        >
          {Array.from({ length: cols }).map((_, c) => (
            <div
              key={c}
              className="h-3 rounded bg-white/[0.05] animate-pulse"
              style={{ width: c === 0 ? '85%' : '60%' }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonAIResponse() {
  return (
    <div className="glass-strong p-5 space-y-4">
      {/* Title line */}
      <div className="h-5 rounded-lg bg-white/[0.08] animate-pulse w-1/2" />
      {/* Paragraph */}
      <Skeleton lines={4} height="h-3" />
      {/* Table skeleton */}
      <div className="mt-2 space-y-2">
        <div className="h-3 rounded bg-orange-500/20 animate-pulse w-full" />
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex gap-3">
            <div className="h-3 rounded bg-white/[0.05] animate-pulse flex-1" />
            <div className="h-3 rounded bg-white/[0.05] animate-pulse flex-1" />
            <div className="h-3 rounded bg-white/[0.05] animate-pulse flex-1" />
            <div className="h-3 rounded bg-white/[0.05] animate-pulse flex-1" />
          </div>
        ))}
      </div>
      {/* Footer line */}
      <Skeleton lines={2} height="h-3" className="mt-3" />
    </div>
  )
}
