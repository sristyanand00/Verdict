// A table of credit movements: questions asked, Arena runs, credits given or taken back.

import { Link } from 'react-router-dom'
import { formatDate } from '../lib/format'
import type { LedgerEntry, LedgerKind } from '../lib/types'

const KIND: Record<LedgerKind, string> = {
  ask: 'Question',
  arena: 'Arena run',
  grant: 'Credits added',
  remove: 'Credits taken back',
  refund: 'Refund (server error)',
}

export function Ledger({ rows, empty }: { rows: LedgerEntry[]; empty: string }) {
  if (rows.length === 0) return <p className="py-6 text-sm text-muted">{empty}</p>
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-line text-left text-xs text-muted">
          <th className="py-2 pr-4 font-medium">When</th>
          <th className="py-2 pr-4 font-medium">What</th>
          <th className="py-2 pr-4 font-medium">Detail</th>
          <th className="py-2 pr-4 text-right font-medium">Credits</th>
          <th className="py-2 text-right font-medium">Balance</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-b border-line/60 align-top">
            <td className="whitespace-nowrap py-2.5 pr-4 text-muted">{formatDate(r.at)}</td>
            <td className="whitespace-nowrap py-2.5 pr-4">{KIND[r.kind]}</td>
            <td className="py-2.5 pr-4 text-muted">
              {r.question ? (
                r.ask_id ? <Link to={`/ask?id=${r.ask_id}`} className="text-ink hover:underline">{r.question}</Link> : <span className="text-ink">{r.question}</span>
              ) : (
                r.note ?? ''
              )}
            </td>
            <td className={`py-2.5 pr-4 text-right font-mono tabular-nums ${r.amount < 0 ? 'text-ink' : 'text-lv-green'}`}>
              {r.amount > 0 ? `+${r.amount}` : r.amount}
            </td>
            <td className="py-2.5 text-right font-mono tabular-nums text-muted">{r.balance_after}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
