// History: every question asked, grouped by day, each with its level. Click one to open it.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { LevelBadge } from '../components/LevelBadge'
import { api } from '../lib/api'
import type { AskSummary, Level } from '../lib/types'

function dayLabel(iso: string) {
  const d = new Date(iso)
  const today = new Date()
  const yesterday = new Date(Date.now() - 86_400_000)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
}

export default function History() {
  const [asks, setAsks] = useState<AskSummary[] | null>(null)
  const [level, setLevel] = useState<Level | 'all'>('all')
  const [search, setSearch] = useState('')

  useEffect(() => {
    api.recentAsks(200).then(setAsks).catch(() => setAsks([]))
  }, [])

  const shown = (asks ?? []).filter((a) => (level === 'all' || a.level === level) && a.question.toLowerCase().includes(search.toLowerCase()))
  const days: [string, AskSummary[]][] = []
  for (const a of shown) {
    const label = dayLabel(a.created_at)
    const last = days[days.length - 1]
    if (last && last[0] === label) last[1].push(a)
    else days.push([label, [a]])
  }

  return (
    <div className="mx-auto max-w-[72rem]">
      <h1 className="mb-1 text-3xl font-bold">History</h1>
      <p className="mb-6 text-muted">Every question asked on this database, newest first.</p>

      <div className="mb-6 flex flex-wrap items-center gap-2 text-sm">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search questions"
          className="mr-2 w-64 rounded-full border border-line bg-surface px-4 py-1.5 focus:border-brand focus:outline-none"
        />
        {(['all', 'trusted', 'review', 'reject'] as const).map((l) => (
          <button
            key={l}
            onClick={() => setLevel(l)}
            className={`rounded-full px-3.5 py-1.5 ${level === l ? 'bg-brand text-on-brand' : 'border border-line text-muted hover:text-ink'}`}
          >
            {l === 'all' ? 'All levels' : l[0].toUpperCase() + l.slice(1)}
          </button>
        ))}
      </div>

      {asks && shown.length === 0 && <div className="rounded-2xl border border-dashed border-line p-10 text-center text-muted">No questions match.</div>}

      {days.map(([label, list]) => (
        <section key={label} className="mb-6">
          <h2 className="mb-2 text-xs font-extrabold uppercase tracking-[0.14em] text-muted">{label}</h2>
          <ul className="overflow-hidden rounded-2xl border border-line">
            {list.map((a) => (
              <li key={a.ask_id} className="border-b border-line last:border-b-0">
                <Link to={`/ask?id=${a.ask_id}`} className="flex items-center gap-4 bg-surface px-5 py-3.5 hover:bg-surface-2">
                  <div className="w-24 shrink-0"><LevelBadge level={a.level} /></div>
                  <span className="min-w-0 flex-1 truncate">{a.question}</span>
                  {a.flagged && <span className="rounded-full bg-accent px-2 py-0.5 text-[0.65rem] font-bold text-on-accent">FLAGGED</span>}
                  <span className="shrink-0 font-mono text-sm font-bold">{a.answer_text ?? <span className="font-sans font-normal text-muted">no answer</span>}</span>
                  <span className="w-14 shrink-0 text-right text-xs text-muted">{new Date(a.created_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
