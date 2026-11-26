import { formatCell } from '../lib/format'

export function ResultTable({ columns, rows, max = 10 }: { columns: string[]; rows: unknown[][]; max?: number }) {
  if (rows.length === 0) return <p className="text-sm text-muted">No rows.</p>
  const shown = rows.slice(0, max)
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full font-mono text-sm">
        {columns.length > 0 && (
          <thead>
            <tr className="bg-surface-2 text-left text-muted">
              {columns.map((c) => <th key={c} className="px-4 py-2 font-semibold">{c}</th>)}
            </tr>
          </thead>
        )}
        <tbody>
          {shown.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {r.map((v, j) => <td key={j} className="px-4 py-2">{formatCell(v)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > max && <p className="border-t border-line px-4 py-2 text-xs text-muted">Showing {max} of {rows.length.toLocaleString('en-US')} rows</p>}
    </div>
  )
}

export function SqlBlock({ sql }: { sql: string }) {
  return (
    <pre className="overflow-x-auto rounded-xl border border-line bg-bg p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words text-ink">
      {sql}
    </pre>
  )
}
