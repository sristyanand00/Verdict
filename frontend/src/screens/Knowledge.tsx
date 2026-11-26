// What Verdict has learned for the current database (GET /api/knowledge).
// Two pages share this file:
//   Metrics   (/metrics):   meanings, the metric definitions the team saved ("revenue = ...")
//   Knowledge (/knowledge): approved examples and known numbers that came from the review queue
// Any user can add a meaning. Only the provider can delete knowledge (the server returns 403 for analysts),
// so delete buttons are shown to the provider only.

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { DatabasePicker } from '../components/DatabasePicker'
import { SqlBlock } from '../components/ResultTable'
import { api } from '../lib/api'
import { useDatabase } from '../lib/database'
import { describeError } from '../lib/errors'
import { formatCell, formatDate } from '../lib/format'
import { useSession } from '../lib/session'
import type { Knowledge as KnowledgeData } from '../lib/types'

type Mode = 'meanings' | 'learned'

export default function Knowledge({ mode }: { mode: Mode }) {
  const { me } = useSession()
  const { current: db, databases } = useDatabase()
  const isAdmin = me?.user.role === 'admin'
  const [data, setData] = useState<KnowledgeData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actionMsg, setActionMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const load = useCallback(() => {
    if (!db) return
    setData(null)
    setError(null)
    api
      .knowledge(db.id)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load the knowledge'))
  }, [db])

  useEffect(load, [load])

  async function remove(kind: 'meanings' | 'examples' | 'known', id: string) {
    setActionMsg(null)
    try {
      await api.deleteKnowledge(kind, id)
      load()
    } catch (e) {
      const d = describeError(e, 'Could not delete it')
      setActionMsg({ ok: false, text: `${d.title}. ${d.text}` })
    }
  }

  async function recheck(id: string) {
    setActionMsg(null)
    try {
      const r = await api.recheckKnown(id)
      setActionMsg(
        r.changed
          ? { ok: false, text: `The number changed: saved ${formatCell(r.saved_value)}, now ${formatCell(r.value_now)}.` }
          : { ok: true, text: `Still the same: ${formatCell(r.value_now)}.` },
      )
      load()
    } catch (e) {
      const d = describeError(e, 'Could not check it again')
      setActionMsg({ ok: false, text: `${d.title}. ${d.text}` })
    }
  }

  return (
    <div className="max-w-[64rem]">
      <h1 className="text-2xl font-semibold">{mode === 'meanings' ? 'Metrics' : 'Knowledge'}</h1>
      <p className="mt-1 text-sm text-muted">
        {mode === 'meanings'
          ? 'What words like "revenue" mean in this database. Verdict adds a matching meaning to the prompt when a question uses the word.'
          : 'Answers approved in the review queue. Similar questions use them as examples, and known numbers are checked against new answers.'}{' '}
        Knowledge never skips the checks.
      </p>
      <div className="mt-4">
        <DatabasePicker />
      </div>

      {actionMsg && <p className={`mt-4 text-sm ${actionMsg.ok ? 'text-lv-green' : 'text-lv-red'}`}>{actionMsg.text}</p>}
      {databases && !db && <p className="mt-8 text-sm text-muted">Pick a database to see what Verdict has learned about it.</p>}
      {error && <p className="mt-8 text-sm text-lv-red">{error}</p>}
      {db && !data && !error && <p className="mt-8 text-sm text-muted">Loading...</p>}

      {data && db && mode === 'meanings' && (
        <>
          <AddMeaning databaseId={db.id} onAdded={load} />
          <section className="mt-10">
            <h2 className="text-sm font-semibold">Saved meanings ({data.meanings.length})</h2>
            {data.meanings.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No meanings saved for {db.name} yet.</p>
            ) : (
              <ul className="mt-2 divide-y divide-line border-y border-line">
                {data.meanings.map((m) => (
                  <li key={m.id} className="flex items-start gap-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-ink">{m.term}</div>
                      <div className="text-sm text-muted">{m.definition}</div>
                      {m.sql_hint && <code className="mt-1 block font-mono text-xs text-brand-text">{m.sql_hint}</code>}
                    </div>
                    <span className="shrink-0 text-xs text-muted">{formatDate(m.created_at)}</span>
                    {isAdmin && <DeleteBtn onClick={() => void remove('meanings', m.id)} />}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      {data && db && mode === 'learned' && (
        <>
          <section className="mt-8">
            <h2 className="text-sm font-semibold">Known numbers ({data.known_numbers.length})</h2>
            <p className="mt-1 text-xs text-muted">Saved when an analyst approved an answer as a number to keep. "Check again" runs its SQL on today's data.</p>
            {data.known_numbers.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No known numbers for {db.name} yet.</p>
            ) : (
              <table className="mt-3 w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs text-muted">
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 text-right font-medium">Value</th>
                    <th className="py-2 pr-4 font-medium">Last checked</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody>
                  {data.known_numbers.map((k) => (
                    <tr key={k.id} className="border-b border-line/60 align-top">
                      <td className="py-2.5 pr-4">
                        <div className="text-ink">{k.name}</div>
                        <div className="text-xs text-muted">{k.question}</div>
                      </td>
                      <td className="py-2.5 pr-4 text-right font-mono tabular-nums text-ink">{formatCell(k.value)}</td>
                      <td className="py-2.5 pr-4 text-muted">
                        {k.last_checked_at ? formatDate(k.last_checked_at) : 'Never'}
                        {k.last_ok === false && <span className="ml-2 text-lv-yellow">changed</span>}
                      </td>
                      <td className="whitespace-nowrap py-2.5 text-right">
                        <button onClick={() => void recheck(k.id)} className="text-sm text-brand-text hover:underline">
                          Check again
                        </button>
                        {isAdmin && <DeleteBtn onClick={() => void remove('known', k.id)} />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="mt-10">
            <h2 className="text-sm font-semibold">Approved examples ({data.examples.length})</h2>
            <p className="mt-1 text-xs text-muted">Up to 3 similar examples are added to the prompt for a new question.</p>
            {data.examples.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No approved examples for {db.name} yet. Approve or fix an item in the review queue to add one.</p>
            ) : (
              <ul className="mt-2 divide-y divide-line border-y border-line">
                {data.examples.map((x) => (
                  <li key={x.id} className="py-3">
                    <div className="flex items-start gap-4">
                      <div className="min-w-0 flex-1 text-ink">{x.question}</div>
                      <span className="shrink-0 text-xs text-muted">{formatDate(x.created_at)}</span>
                      {isAdmin && <DeleteBtn onClick={() => void remove('examples', x.id)} />}
                    </div>
                    <details className="mt-1">
                      <summary className="cursor-pointer text-xs text-brand-text">SQL</summary>
                      <div className="mt-2">
                        <SqlBlock sql={x.sql} />
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  )
}

function DeleteBtn({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="ml-3 shrink-0 text-sm text-muted hover:text-lv-red">
      Delete
    </button>
  )
}

function AddMeaning({ databaseId, onAdded }: { databaseId: string; onAdded: () => void }) {
  const [term, setTerm] = useState('')
  const [definition, setDefinition] = useState('')
  const [hint, setHint] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!term.trim() || !definition.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api.addMeaning({ term: term.trim(), definition: definition.trim(), sql_hint: hint.trim() || undefined }, databaseId)
      setTerm('')
      setDefinition('')
      setHint('')
      onAdded()
    } catch (err) {
      const d = describeError(err, 'Could not save the meaning')
      setError(`${d.title}. ${d.text}`)
    } finally {
      setBusy(false)
    }
  }

  const input = 'rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-muted/60 focus:border-brand focus:outline-none'
  return (
    <form onSubmit={submit} className="mt-8">
      <h2 className="text-sm font-semibold">Add a meaning</h2>
      <div className="mt-2 grid gap-2 md:grid-cols-[12rem_1fr]">
        <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Word, e.g. revenue" aria-label="Word" className={input} />
        <input
          value={definition}
          onChange={(e) => setDefinition(e.target.value)}
          placeholder="What it means, e.g. sum of payment_value, delivered orders only"
          aria-label="Meaning"
          className={input}
        />
        <span className="hidden md:block" />
        <input value={hint} onChange={(e) => setHint(e.target.value)} placeholder="SQL hint (optional), e.g. SUM(p.payment_value)" aria-label="SQL hint" className={`${input} font-mono`} />
      </div>
      {error && <p className="mt-2 text-sm text-lv-red">{error}</p>}
      <button type="submit" disabled={busy || !term.trim() || !definition.trim()} className="mt-3 rounded-md bg-brand px-4 py-1.5 text-sm font-semibold text-on-brand disabled:opacity-50">
        {busy ? 'Saving...' : 'Save meaning'}
      </button>
    </form>
  )
}
