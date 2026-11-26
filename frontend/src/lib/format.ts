// Formatting helpers for numbers, ranges and result cells.

export function formatCell(v: unknown): string {
  if (v === null || v === undefined) return 'NULL'
  if (typeof v === 'number') {
    return Number.isInteger(v) ? v.toLocaleString('en-US') : v.toLocaleString('en-US', { maximumFractionDigits: 2 })
  }
  return String(v)
}

export function percent(x: number): string {
  return `${Math.round(x * 100)}%`
}

export function range(low: number, high: number): string {
  return `${percent(low)} to ${percent(high)}`
}

export function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}

export function timeAgo(iso: string): string {
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 60) return 'just now'
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  return `${h} h ago`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
