// Data: the databases this account can use (GET /api/databases), their tables and columns,
// and uploading a CSV, Excel or SQLite file. An upload is private to the person who uploaded it.
// The server may have uploads turned off (403); its message is shown as it is.
// The provider also sets the server defaults here (PUT /api/settings is admin only).

import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useDatabase } from '../lib/database'
import { describeError } from '../lib/errors'
import { useSession } from '../lib/session'
import type { DatabaseSchema, ModelInfo, Settings } from '../lib/types'

export default function Data() {
  const { me } = useSession()
  const { databases, current, error, choose, reload } = useDatabase()
  const [openId, setOpenId] = useState<string | null>(null)

  return (
    <div className="max-w-[64rem]">
      <h1 className="text-2xl font-semibold">Data</h1>
      <p className="mt-1 text-sm text-muted">The databases you can ask about. Verdict only reads them; it never changes your data.</p>

      {error && <p className="mt-6 text-sm text-lv-red">{error}</p>}
      {!databases && !error && <p className="mt-6 text-sm text-muted">Loading...</p>}
      {databases && databases.length === 0 && <p className="mt-6 text-sm text-muted">The server lists no databases.</p>}

      {databases && databases.length > 0 && (
        <ul className="mt-6 divide-y divide-line border-y border-line">
          {databases.map((d) => (
            <li key={d.id} className="py-3">
              <div className="flex flex-wrap items-start gap-4">
                <div className="min-w-0 flex-1">
                  <div className={d.available ? 'text-ink' : 'text-muted'}>
                    {d.name}
                    {d.source === 'upload' && <span className="ml-2 text-xs text-muted">your upload</span>}
                    {current?.id === d.id && <span className="ml-2 text-xs text-brand-text">in use</span>}
                  </div>
                  {d.description && <div className="text-sm text-muted">{d.description}</div>}
                  <div className="text-xs text-muted">
                    {d.available ? `${d.tables_count} ${d.tables_count === 1 ? 'table' : 'tables'}` : 'Not available: the file is not on the server.'}
                  </div>
                </div>
                {d.available && (
                  <div className="flex shrink-0 gap-3 text-sm">
                    <button onClick={() => setOpenId(openId === d.id ? null : d.id)} className="text-brand-text hover:underline">
                      {openId === d.id ? 'Hide tables' : 'Show tables'}
                    </button>
                    {current?.id !== d.id && (
                      <button onClick={() => choose(d.id)} className="text-muted hover:text-ink">
                        Use this
                      </button>
                    )}
                  </div>
                )}
              </div>
              {openId === d.id && <Schema id={d.id} />}
            </li>
          ))}
        </ul>
      )}

      <Upload
        onDone={async (id) => {
          await reload()
          choose(id)
        }}
      />

      {me?.user.role === 'admin' && <ServerDefaults />}
    </div>
  )
}

function Schema({ id }: { id: string }) {
  const [schema, setSchema] = useState<DatabaseSchema | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .schema(id)
      .then(setSchema)
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load the tables'))
  }, [id])

  if (error) return <p className="mt-3 text-sm text-lv-red">{error}</p>
  if (!schema) return <p className="mt-3 text-sm text-muted">Loading tables...</p>
  if (schema.tables.length === 0) return <p className="mt-3 text-sm text-muted">This database has no tables.</p>
  return (
    <div className="mt-3 grid gap-x-8 gap-y-4 md:grid-cols-2">
      {schema.tables.map((t) => (
        <div key={t.name} className="min-w-0">
          <div className="text-sm">
            <span className="font-mono text-ink">{t.name}</span>
            <span className="ml-2 text-xs text-muted">{t.row_count.toLocaleString('en-US')} rows</span>
          </div>
          <div className="mt-1 font-mono text-xs leading-relaxed text-muted">
            {t.columns.map((c) => (
              <span key={c.name} className="mr-3 inline-block">
                {c.name}
                {c.type && <span className="text-muted/60"> {c.type.toLowerCase()}</span>}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function Upload({ onDone }: { onDone: (id: string) => Promise<void> }) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  async function pick(file: File | undefined) {
    if (!file) return
    setBusy(true)
    setMsg(null)
    try {
      const r = await api.upload(file)
      setMsg({ ok: true, text: `Uploaded ${r.name}: ${r.tables_count} ${r.tables_count === 1 ? 'table' : 'tables'}. It is now the database in use.` })
      await onDone(r.id)
    } catch (e) {
      const d = describeError(e, 'Could not upload the file')
      setMsg({ ok: false, text: `${d.title}. ${d.text}` })
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <section className="mt-12">
      <h2 className="text-sm font-semibold">Upload your own data</h2>
      <p className="mt-1 text-sm text-muted">A CSV, Excel (XLSX) or SQLite file, up to 50 MB. Only you and the provider can see it. The server may delete old uploads.</p>
      <input ref={input} type="file" accept=".csv,.xlsx,.sqlite,.db,.sqlite3" className="hidden" onChange={(e) => void pick(e.target.files?.[0])} />
      <button
        onClick={() => input.current?.click()}
        disabled={busy}
        className="mt-3 rounded-md border border-line px-4 py-1.5 text-sm text-ink hover:border-brand disabled:opacity-50"
      >
        {busy ? 'Uploading...' : 'Choose a file'}
      </button>
      {msg && <p className={`mt-2 text-sm ${msg.ok ? 'text-lv-green' : 'text-lv-red'}`}>{msg.text}</p>}
    </section>
  )
}

// Provider only: the defaults every account starts with.
function ServerDefaults() {
  const { databases } = useDatabase()
  const [settings, setSettings] = useState<Settings | null>(null)
  const [models, setModels] = useState<ModelInfo[] | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    Promise.all([api.settings(), api.models()])
      .then(([s, m]) => {
        setSettings(s)
        setModels(m)
      })
      .catch((e) => setMsg({ ok: false, text: e instanceof Error ? e.message : 'Could not load the settings' }))
  }, [])

  async function save(change: Partial<Settings>) {
    setMsg(null)
    try {
      setSettings(await api.saveSettings(change))
      setMsg({ ok: true, text: 'Saved.' })
    } catch (e) {
      const d = describeError(e, 'Could not save the settings')
      setMsg({ ok: false, text: `${d.title}. ${d.text}` })
    }
  }

  const select = 'rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink focus:border-brand focus:outline-none'
  return (
    <section className="mt-12 border-t border-line pt-8">
      <h2 className="text-sm font-semibold">Server defaults (provider only)</h2>
      <p className="mt-1 text-sm text-muted">Shared by every account. Each analyst can still pick another database for themselves.</p>
      {settings && models && (
        <div className="mt-4 flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2 text-muted">
            Default database
            <select value={settings.database_id} onChange={(e) => void save({ database_id: e.target.value })} className={select}>
              {(databases ?? [])
                .filter((d) => d.source === 'preloaded')
                .map((d) => (
                  <option key={d.id} value={d.id} disabled={!d.available}>
                    {d.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-muted">
            Model for Ask
            <select value={settings.model} onChange={(e) => void save({ model: e.target.value })} className={select}>
              {models
                .filter((m) => m.kind === 'own')
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                    {m.reachable ? '' : ' (not reachable)'}
                  </option>
                ))}
            </select>
          </label>
        </div>
      )}
      {msg && <p className={`mt-2 text-sm ${msg.ok ? 'text-lv-green' : 'text-lv-red'}`}>{msg.text}</p>}
    </section>
  )
}
