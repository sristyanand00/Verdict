// The analyst's own account: credits left, what they were used on, and what each action costs.

import { useEffect, useState } from 'react'
import { Ledger } from '../components/Ledger'
import { formatDate } from '../lib/format'
import { api } from '../lib/api'
import { useSession } from '../lib/session'
import type { LedgerEntry } from '../lib/types'

const plural = (n: number) => (n === 1 ? 'credit' : 'credits')

export default function Account() {
  const { me, logout } = useSession()
  const [rows, setRows] = useState<LedgerEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const balance = me?.credits.balance

  useEffect(() => {
    api.myUsage().then(setRows).catch((e) => setError(e instanceof Error ? e.message : 'Could not load your usage'))
  }, [balance])

  if (!me) return null
  const { user, credits, prices } = me

  return (
    <div className="max-w-[56rem]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{user.name}</h1>
          <p className="mt-1 text-sm text-muted">
            {user.email} · {user.role === 'admin' ? 'Provider' : 'Analyst'} · member since {formatDate(user.created_at)}
          </p>
        </div>
        <button onClick={() => void logout()} className="rounded-md border border-line px-3 py-1.5 text-sm text-muted hover:text-ink">
          Log out
        </button>
      </div>

      <dl className="mt-8 grid grid-cols-3 border-y border-line">
        <Stat label="Credits left" value={credits.balance} strong />
        <Stat label="Used this month" value={credits.used_this_month} />
        <Stat label="Used in total" value={credits.used_total} />
      </dl>
      {user.role === 'admin' && <p className="mt-3 text-sm text-muted">As the provider, your own questions are free and are not listed here.</p>}
      {user.role !== 'admin' && credits.balance < prices.ask && (
        <p className="mt-3 text-sm text-lv-yellow">You do not have enough credits to ask a question. Ask your provider for more.</p>
      )}

      <section className="mt-10">
        <h2 className="text-sm font-semibold">What costs credits</h2>
        <ul className="mt-2 space-y-1 text-sm text-muted">
          <li>
            One question on the Ask page: <span className="text-ink">{prices.ask} {plural(prices.ask)}</span>
          </li>
          <li>
            Each outside model in a live Model Arena run:{' '}
            <span className="text-ink">{prices.arena_outside_model} {plural(prices.arena_outside_model)}</span>
          </li>
          <li>Reviewing, approving and teaching Verdict: free</li>
        </ul>
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold">Usage</h2>
        {error && <p className="mt-2 text-sm text-lv-red">{error}</p>}
        {!rows && !error && <p className="mt-2 text-sm text-muted">Loading...</p>}
        {rows && <Ledger rows={rows} empty="Nothing yet. Credits you use will show up here." />}
      </section>

    </div>
  )
}

function Stat({ label, value, strong }: { label: string; value: number; strong?: boolean }) {
  return (
    <div className="border-r border-line py-4 pl-4 first:pl-0 last:border-r-0">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`mt-1 font-mono tabular-nums ${strong ? 'text-3xl text-ink' : 'text-2xl text-ink/80'}`}>{value.toLocaleString('en-US')}</dd>
    </div>
  )
}
