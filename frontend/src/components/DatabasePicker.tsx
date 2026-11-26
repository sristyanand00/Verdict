// A select for the current database. Databases whose file is not on the server are shown but cannot be picked.

import { useDatabase } from '../lib/database'

export function DatabasePicker({ disabled = false }: { disabled?: boolean }) {
  const { databases, current, error, choose } = useDatabase()

  if (error) return <span className="text-xs text-lv-red">Databases: {error}</span>
  if (!databases) return <span className="text-xs text-muted">Loading databases...</span>
  if (databases.length === 0) return <span className="text-xs text-muted">The server lists no databases.</span>

  return (
    <label className="flex items-center gap-2 text-xs text-muted">
      Database
      <select
        value={current?.id ?? ''}
        disabled={disabled}
        onChange={(e) => choose(e.target.value)}
        className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink focus:border-brand focus:outline-none disabled:opacity-60"
      >
        {!current && <option value="">Pick a database</option>}
        {databases.map((d) => (
          <option key={d.id} value={d.id} disabled={!d.available}>
            {d.name}
            {d.source === 'upload' ? ' (your upload)' : ''}
            {d.available ? '' : ' (not available)'}
          </option>
        ))}
      </select>
      {current?.description && <span className="hidden max-w-[28rem] truncate lg:inline">{current.description}</span>}
    </label>
  )
}
