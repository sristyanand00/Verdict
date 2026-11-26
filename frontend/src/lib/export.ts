// Export an answer as CSV, SQL or a short text receipt, built in the browser from the answer the server returned.

import { formatCell } from './format'
import type { AskResponse } from './types'

const LEVEL_WORD = { trusted: 'Trusted', review: 'Review', reject: 'Reject' } as const

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return ''
  const s = String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function toCsv(a: AskResponse): string {
  const lines = [a.columns.map(csvCell).join(',')]
  for (const r of a.rows) lines.push(r.map(csvCell).join(','))
  return lines.join('\n') + '\n'
}

export function toSql(a: AskResponse): string {
  return `-- ${a.question}\n-- Verdict: ${LEVEL_WORD[a.level]}. Database: ${a.database_id}.\n${a.sql ?? ''}\n`
}

export function toReceipt(a: AskResponse): string {
  const out: string[] = []
  out.push(`Question: ${a.question}`)
  out.push(`Answer: ${a.answer_text ?? (a.rows[0] ? a.rows[0].map(formatCell).join(', ') : 'none')}`)
  out.push(`Verdict: ${LEVEL_WORD[a.level]} (${a.reasons.map((r) => r.text).join('; ')})`)
  out.push(`Database: ${a.database_id}`)
  if (a.lineage) {
    out.push(`Formula: ${a.lineage.formula}`)
    out.push(`Tables: ${a.lineage.tables.join(', ')}`)
    if (a.lineage.filters.length) out.push(`Filters: ${a.lineage.filters.join(' and ')}`)
    if (a.lineage.period) out.push(`Period: ${a.lineage.period}`)
  }
  if (a.knowledge_used.length) out.push(`Definitions used: ${a.knowledge_used.join('; ')}`)
  out.push(`Checks: ${a.checks.map((c) => `${c.name} ${c.status}`).join(', ')}`)
  out.push(`Model: ${a.model_label}`)
  out.push(`Checked by Verdict on ${new Date(a.created_at).toLocaleString('en-GB')}`)
  if (a.sql) out.push('', 'SQL:', a.sql)
  return out.join('\n') + '\n'
}

function slug(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 50) || 'answer'
}

export function download(a: AskResponse, kind: 'csv' | 'sql' | 'receipt') {
  const text = kind === 'csv' ? toCsv(a) : kind === 'sql' ? toSql(a) : toReceipt(a)
  const ext = kind === 'csv' ? 'csv' : kind === 'sql' ? 'sql' : 'txt'
  const type = kind === 'csv' ? 'text/csv' : 'text/plain'
  const url = URL.createObjectURL(new Blob([text], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${slug(a.question)}${kind === 'receipt' ? '-receipt' : ''}.${ext}`
  link.click()
  URL.revokeObjectURL(url)
}

export async function copyReceipt(a: AskResponse): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(toReceipt(a))
    return true
  } catch {
    return false
  }
}
