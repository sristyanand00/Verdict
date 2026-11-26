// Provider panel: every account, its credits and usage. The provider adds or takes back
// credits and can turn an account off. Only users with role "admin" can open it.

import { Fragment, useCallback, useEffect, useState, type FormEvent } from 'react'
import { Ledger } from '../components/Ledger'
import { formatDate } from '../lib/format'
import { api } from '../lib/api'
import { useSession } from '../lib/session'
import type { AdminUserRow, LedgerEntry } from '../lib/types'

export default function Admin() {
  const { me, refresh } = useSession()
  const [users, setUsers] = useState<AdminUserRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  const load = useCallback(() => {
    api
      .adminUsers()
      .then((u) => {
        setUsers(u)
        setError(null)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load the accounts'))
  }, [])

  useEffect(load, [load])

  async function changed() {
    load()
    await refresh()
  }

  const q = query.trim().toLowerCase()
  const shown = (users ?? []).filter((u) => !q || u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q))
  const totals = (users ?? []).reduce((t, u) => ({ balance: t.balance + u.balance, used: t.used + u.used_total }), { balance: 0, used: 0 })

  return (
    <div className="max-w-[72rem]">
      <h1 className="text-2xl font-semibold">Accounts</h1>
      <p className="mt-1 text-sm text-muted">Everyone who uses Verdict through you. Add credits, take them back, or turn an account off.</p>

      {users && (
        <p className="mt-6 text-sm text-muted">
          <span className="text-ink">{users.length}</span> {users.length === 1 ? 'account' : 'accounts'} ·{' '}
          <span className="text-ink">{totals.balance.toLocaleString('en-US')}</span> credits not yet used ·{' '}
          <span className="text-ink">{totals.used.toLocaleString('en-US')}</span> used so far
        </p>
      )}

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search by name or email"
        className="mt-4 w-full max-w-xs rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-muted/60 focus:border-brand focus:outline-none"
      />

      {error && <p className="mt-4 text-sm text-lv-red">{error}</p>}
      {!users && !error && <p className="mt-4 text-sm text-muted">Loading...</p>}

      {users && (
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="py-2 pr-4 font-medium">Account</th>
              <th className="py-2 pr-4 font-medium">Role</th>
              <th className="py-2 pr-4 text-right font-medium">Credits left</th>
              <th className="py-2 pr-4 text-right font-medium">Used</th>
              <th className="py-2 pr-4 text-right font-medium">Questions</th>
              <th className="py-2 pr-4 font-medium">Last active</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr>
                <td colSpan={7} className="py-6 text-muted">
                  {q ? 'No account matches that search.' : 'No accounts yet.'}
                </td>
              </tr>
            )}
            {shown.map((u) => (
              <Fragment key={u.id}>
                <tr className={`border-b border-line/60 ${open === u.id ? 'bg-surface' : ''}`}>
                  <td className="py-2.5 pr-4">
                    <div className={u.active ? 'text-ink' : 'text-muted line-through'}>{u.name}</div>
                    <div className="text-xs text-muted">{u.email}</div>
                  </td>
                  <td className="py-2.5 pr-4 text-muted">
                    {u.role === 'admin' ? 'Provider' : 'Analyst'}
                    {!u.active && <span className="ml-2 text-lv-red">Off</span>}
                  </td>
                  <td className={`py-2.5 pr-4 text-right font-mono tabular-nums ${u.role === 'admin' ? 'text-muted' : u.balance === 0 ? 'text-lv-yellow' : 'text-ink'}`}>
                    {u.role === 'admin' ? <span className="font-sans">free</span> : u.balance}
                  </td>
                  <td className="py-2.5 pr-4 text-right font-mono tabular-nums text-muted">{u.used_total}</td>
                  <td className="py-2.5 pr-4 text-right font-mono tabular-nums text-muted">{u.asks_count}</td>
                  <td className="py-2.5 pr-4 text-muted">{u.last_active_at ? formatDate(u.last_active_at) : 'Never'}</td>
                  <td className="py-2.5 text-right">
                    <button onClick={() => setOpen(open === u.id ? null : u.id)} className="text-sm text-brand-text hover:underline">
                      {open === u.id ? 'Close' : 'Manage'}
                    </button>
                  </td>
                </tr>
                {open === u.id && (
                  <tr className="border-b border-line bg-surface">
                    <td colSpan={7} className="px-4 pb-6 pt-2">
                      <Manage user={u} isSelf={u.id === me?.user.id} onChanged={changed} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}

    </div>
  )
}

function Manage({ user, isSelf, onChanged }: { user: AdminUserRow; isSelf: boolean; onChanged: () => Promise<void> }) {
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [rows, setRows] = useState<LedgerEntry[] | null>(null)

  useEffect(() => {
    api.adminUsage(user.id).then(setRows).catch(() => setRows([]))
  }, [user.id, user.balance])

  async function apply(sign: 1 | -1, e?: FormEvent) {
    e?.preventDefault()
    const n = Number(amount)
    if (!Number.isInteger(n) || n <= 0) {
      setMsg({ ok: false, text: 'Enter a whole number of credits, more than 0.' })
      return
    }
    setBusy(true)
    setMsg(null)
    try {
      await api.adminCredits(user.id, sign * n, note.trim())
      setMsg({ ok: true, text: sign > 0 ? `Added ${n} credits.` : `Took back ${n} credits.` })
      setAmount('')
      setNote('')
      await onChanged()
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : 'Could not change the credits.' })
    } finally {
      setBusy(false)
    }
  }

  async function toggle() {
    setBusy(true)
    setMsg(null)
    try {
      await api.adminSetActive(user.id, !user.active)
      await onChanged()
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : 'Could not change the account.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[18rem_1fr]">
      <div>
        <form onSubmit={(e) => apply(1, e)} className="flex flex-col gap-2">
          <label className="text-xs text-muted" htmlFor={`amt-${user.id}`}>
            Credits
          </label>
          <input
            id={`amt-${user.id}`}
            inputMode="numeric"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="e.g. 50"
            className="rounded-md border border-line bg-bg px-3 py-1.5 font-mono text-sm text-ink focus:border-brand focus:outline-none"
          />
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional), e.g. December plan"
            className="rounded-md border border-line bg-bg px-3 py-1.5 text-sm text-ink placeholder:text-muted/60 focus:border-brand focus:outline-none"
          />
          <div className="mt-1 flex gap-2">
            <button type="submit" disabled={busy} className="rounded-md bg-brand px-3 py-1.5 text-sm font-semibold text-on-brand disabled:opacity-50">
              Add credits
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => apply(-1)}
              className="rounded-md border border-line px-3 py-1.5 text-sm text-muted hover:text-ink disabled:opacity-50"
            >
              Take back
            </button>
          </div>
        </form>
        {msg && <p className={`mt-2 text-sm ${msg.ok ? 'text-lv-green' : 'text-lv-red'}`}>{msg.text}</p>}

        {!isSelf && (
          <button onClick={toggle} disabled={busy} className="mt-6 text-sm text-muted hover:text-lv-red disabled:opacity-50">
            {user.active ? 'Turn this account off' : 'Turn this account back on'}
          </button>
        )}
      </div>
      <div className="min-w-0">
        <h3 className="text-xs font-medium text-muted">Usage of {user.name}</h3>
        {!rows ? <p className="py-4 text-sm text-muted">Loading...</p> : <Ledger rows={rows} empty="No credit movements yet." />}
      </div>
    </div>
  )
}
