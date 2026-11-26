// Saved: answers the analyst named and kept. Re-run goes through the same verifier
// and says whether the number changed.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { LevelBadge } from '../components/LevelBadge'
import { api, notifyChanged } from '../lib/api'
import { timeAgo } from '../lib/format'
import type { SavedItem } from '../lib/types'

export default function Saved() {
  const [items, setItems] = useState<SavedItem[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.saved().then(setItems).catch((e) => setError(e instanceof Error ? e.message : 'Could not load saved answers'))
  }, [])

  async function rerun(id: string) {
    setBusy(id)
    try {
      setError(null)
      const s = await api.rerunSaved(id)
      setItems((list) => (list ?? []).map((x) => (x.id === id ? { ...s } : x)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not run it again')
    } finally {
      notifyChanged()
      setBusy(null)
    }
  }

  async function remove(id: string) {
    await api.deleteSaved(id)
    setItems((list) => (list ?? []).filter((x) => x.id !== id))
  }

  return (
    <div className="mx-auto max-w-[72rem]">
      <h1 className="mb-1 text-3xl font-bold">Saved</h1>
      <p className="mb-6 text-muted">Answers you named and kept. Re-run one to check whether the number has changed.</p>

      {error && <p className="rounded-xl border border-lv-red/50 bg-lv-red-tint p-4 text-sm">{error}</p>}

      {items && items.length === 0 && (
        <div className="rounded-2xl border border-dashed border-line p-10 text-center text-muted">
          Nothing saved yet. Open a receipt on the <Link to="/ask" className="text-brand-text hover:underline">Ask page</Link> and press Save.
        </div>
      )}

      <ul className="space-y-3">
        {(items ?? []).map((s) => (
          <li key={s.id} className="flex flex-wrap items-center gap-4 rounded-2xl border border-line bg-surface px-5 py-4">
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex items-center gap-3">
                <span className="text-lg font-semibold">{s.name}</span>
                <LevelBadge level={s.level} />
              </div>
              <div className="text-xs text-muted">
                Checked {timeAgo(s.last_run_at)}.{' '}
                {s.changed ? <b className="text-lv-yellow">The number changed since it was saved.</b> : 'Same number as when saved.'}
              </div>
            </div>
            <span className="font-mono text-2xl font-bold">{s.last_value ?? '--'}</span>
            <div className="flex gap-2">
              <button onClick={() => rerun(s.id)} disabled={busy === s.id} className="rounded-full bg-brand px-4 py-1.5 text-sm font-bold text-on-brand disabled:opacity-50">
                {busy === s.id ? 'Running...' : 'Re-run'}
              </button>
              <Link to={`/ask?id=${s.ask_id}`} className="rounded-full border border-line px-4 py-1.5 text-sm hover:border-brand">Open</Link>
              <button onClick={() => remove(s.id)} className="rounded-full border border-line px-4 py-1.5 text-sm text-muted hover:border-lv-red hover:text-lv-red">Delete</button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
