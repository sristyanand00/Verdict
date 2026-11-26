// The verdict stamp. Three levels only. Always shows the word, never colour alone.
// "Two meanings" and "not in the data" are reasons inside Review or Reject, shown with ReasonChip.

import type { ReactNode } from 'react'

export type Level = 'trusted' | 'review' | 'reject'

const STYLE: Record<Level, { label: string; cls: string }> = {
  trusted: { label: 'Trusted', cls: 'text-lv-green bg-lv-green-tint' },
  review: { label: 'Review', cls: 'text-lv-yellow bg-lv-yellow-tint' },
  reject: { label: 'Reject', cls: 'text-lv-red bg-lv-red-tint' },
}

export function LevelBadge({ level, stamp = false, big = false }: { level: Level; stamp?: boolean; big?: boolean }) {
  const s = STYLE[level]
  const size = big ? 'px-4 py-2 text-base gap-2.5' : 'px-2.5 py-1 text-[0.6875rem] gap-1.5'
  return (
    <span
      className={`inline-flex items-center rounded-md border-2 border-current font-black uppercase tracking-[0.14em] ${size} ${s.cls} ${stamp ? '-rotate-3' : ''}`}
    >
      <span className={`rounded-full bg-current ${big ? 'h-2.5 w-2.5' : 'h-2 w-2'}`} />
      {s.label}
    </span>
  )
}

export function ReasonChip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-line bg-surface-2 px-2.5 py-0.5 text-xs text-ink">
      {children}
    </span>
  )
}
