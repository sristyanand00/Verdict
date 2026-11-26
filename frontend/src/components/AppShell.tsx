// Global layout for the working pages: a left sidebar with one flat list of pages,
// the open review count, the current database and model, and the logged-in account with
// its credits. The provider (role "admin") also sees the Accounts page.

import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../lib/api'
import { useDatabase } from '../lib/database'
import { useSession } from '../lib/session'
import { Logo } from './Logo'

const PAGES: { to: string; label: string }[] = [
  { to: '/ask', label: 'Ask' },
  { to: '/history', label: 'History' },
  { to: '/saved', label: 'Saved' },
  { to: '/data', label: 'Data' },
  { to: '/metrics', label: 'Metrics' },
  { to: '/review', label: 'Review queue' },
  { to: '/knowledge', label: 'Knowledge' },
  { to: '/trust', label: 'Trust Report' },
  { to: '/arena', label: 'Model Arena' },
]

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center justify-between rounded-md px-3 py-2 text-sm ${isActive ? 'bg-brand text-on-brand' : 'text-muted hover:bg-surface-2 hover:text-ink'}`

export function AppShell() {
  const { me } = useSession()
  const { current, databases } = useDatabase()
  const [reviewCount, setReviewCount] = useState<number | null>(null)
  const [modelLabel, setModelLabel] = useState<string | null>(null)

  // the model the server uses for Ask (GET /api/settings), shown by its label from GET /api/models
  useEffect(() => {
    Promise.all([api.settings(), api.models()])
      .then(([s, models]) => setModelLabel(models.find((m) => m.id === s.model)?.label ?? s.model))
      .catch(() => setModelLabel(null))
  }, [])

  useEffect(() => {
    const load = () =>
      api
        .reviewList('open')
        .then((d) => setReviewCount(d.open_counts.review + d.open_counts.reject + d.items.filter((i) => i.level === 'trusted').length))
        .catch(() => setReviewCount(null))
    load()
    window.addEventListener('verdict:changed', load)
    return () => window.removeEventListener('verdict:changed', load)
  }, [])

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-line bg-surface px-3 py-5">
        <div className="px-2">
          <Logo />
        </div>
        <nav className="mt-8 flex flex-col gap-0.5">
          {PAGES.map((p) => (
            <NavLink key={p.to} to={p.to} className={linkClass}>
              {p.label}
              {p.to === '/review' && reviewCount !== null && reviewCount > 0 && (
                <span className="rounded-full bg-accent px-1.5 text-[0.6875rem] font-bold text-on-accent">{reviewCount}</span>
              )}
            </NavLink>
          ))}
          {me?.user.role === 'admin' && (
            <>
              <div className="mx-3 my-3 h-px bg-line" />
              <NavLink to="/admin" className={linkClass}>
                Accounts
              </NavLink>
            </>
          )}
        </nav>
        <div className="flex-1" />
        <div className="px-3 text-xs text-muted">
          <div className="truncate">
            Database <span className="text-ink">{current?.name ?? (databases ? 'none picked' : 'loading...')}</span>
          </div>
          {modelLabel && (
            <div className="mt-0.5 truncate" title={modelLabel}>
              Model <span className="text-ink">{modelLabel}</span>
            </div>
          )}
        </div>
        {me && (
          <NavLink to="/account" className={({ isActive }) => `mt-4 block rounded-md border px-3 py-2.5 ${isActive ? 'border-brand' : 'border-line hover:border-muted/50'}`}>
            <div className="truncate text-sm text-ink">{me.user.name}</div>
            {me.user.role === 'admin' ? (
              <div className="mt-0.5 text-xs text-muted">Provider, questions are free</div>
            ) : (
              <div className={`mt-0.5 text-xs ${me.credits.balance < me.prices.ask ? 'text-lv-yellow' : 'text-muted'}`}>
                <span className="font-mono tabular-nums">{me.credits.balance.toLocaleString('en-US')}</span> credits left
              </div>
            )}
          </NavLink>
        )}
      </aside>
      <main className="min-w-0 flex-1 px-6 py-8 xl:px-12">
        <div className="mx-auto w-full max-w-[100rem]">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
