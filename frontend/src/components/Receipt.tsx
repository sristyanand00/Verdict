// The Trust Receipt: why Verdict gave this level and where the number came from.
// SQL, result, the 8 attempts, the checks that ran, answer lineage, definitions used,
// tested trust, export and save, and the event log.

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { copyReceipt, download } from '../lib/export'
import { formatCell, formatDate, percent, range, seconds, timeAgo } from '../lib/format'
import { GROUP_COLORS, groupLetter } from '../lib/groups'
import type { AskEvent, AskResponse, CheckStatus } from '../lib/types'
import { LevelBadge } from './LevelBadge'
import { ResultTable, SqlBlock } from './ResultTable'


const STATUS_STYLE: Record<CheckStatus, string> = {
  pass: 'bg-lv-green-tint text-lv-green',
  fail: 'bg-lv-red-tint text-lv-red',
  off: 'bg-lv-slate-tint text-lv-slate',
  info: 'border border-line text-muted',
}

// "off" must never read as passed, so it says plainly that the check did not run.
const STATUS_LABEL: Record<CheckStatus, string> = { pass: 'PASS', fail: 'FAIL', off: 'NOT RUN', info: 'INFO' }

export function AttemptDots({ ask }: { ask: AskResponse }) {
  return (
    <div className="flex flex-wrap gap-2" aria-label="Attempts">
      {ask.attempts.map((t) => {
        const grouped = t.kind === 'sql' && t.status === 'ok' && t.group !== null
        const color = grouped ? GROUP_COLORS[t.group! % GROUP_COLORS.length] : t.kind === 'cannot_answer' ? 'var(--color-lv-slate)' : 'var(--color-lv-red)'
        const label = grouped
          ? `Attempt ${t.index + 1}: group ${groupLetter(t.group!)}`
          : t.kind === 'cannot_answer'
            ? `Attempt ${t.index + 1}: said it cannot be answered`
            : t.kind === 'empty'
              ? `Attempt ${t.index + 1}: wrote nothing`
              : `Attempt ${t.index + 1}: ${t.status}${t.error ? `, ${t.error}` : ''}`
        return (
          <span
            key={t.index}
            title={label}
            aria-label={label}
            className="grid h-7 w-7 place-items-center rounded-full border-2 text-[0.6rem] font-black"
            style={grouped ? { background: color, borderColor: color, color: '#030407' } : { borderColor: color, color }}
          >
            {grouped ? groupLetter(t.group!) : t.kind === 'cannot_answer' ? '?' : 'x'}
          </span>
        )
      })}
    </div>
  )
}

export function Receipt({ ask, onClose }: { ask: AskResponse; onClose: () => void }) {
  const [openGroup, setOpenGroup] = useState<number | null>(null)
  const [events, setEvents] = useState<AskEvent[] | null>(null)
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showLog, setShowLog] = useState(false)
  const [copied, setCopied] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState(ask.question.replace(/\?$/, ''))
  const [savedOk, setSavedOk] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const loadEvents = useCallback(() => {
    api
      .askEvents(ask.ask_id)
      .then((ev) => {
        setEvents(ev)
        setEventsError(null)
      })
      .catch((e) => setEventsError(e instanceof Error ? e.message : 'Could not load the event log'))
  }, [ask.ask_id])

  useEffect(loadEvents, [loadEvents])

  async function copy() {
    setCopied(await copyReceipt(ask))
    setTimeout(() => setCopied(false), 1800)
  }

  async function save() {
    if (!saveName.trim()) return
    try {
      setSaveError(null)
      await api.save(ask.ask_id, saveName.trim())
      setSavedOk(true)
      setSaveOpen(false)
      loadEvents()
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Could not save it')
    }
  }

  const hasAnswer = ask.sql !== null && ask.columns.length > 0
  const meaningsUsed = ask.knowledge_used.filter((k) => !k.startsWith('Approved example'))

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Receipt">
      <button aria-label="Close receipt" onClick={onClose} className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <aside className="anim-slide relative h-full w-full max-w-[48rem] overflow-y-auto border-l border-brand/40 bg-surface p-7 shadow-[-30px_0_80px_-20px_rgba(21,88,201,.5)]">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="mb-2 text-xs font-extrabold uppercase tracking-[0.14em] text-muted">Receipt</div>
            <h2 className="text-xl font-bold">"{ask.question}"</h2>
          </div>
          <div className="flex items-center gap-3">
            <LevelBadge level={ask.level} />
            <button onClick={onClose} className="rounded-full border border-line px-3 py-1 text-sm text-muted hover:text-ink">Close</button>
          </div>
        </div>

        {/* actions first, so they are easy to find */}
        {hasAnswer && (
          <div className="mb-7 flex flex-wrap gap-2">
            <ActionBtn onClick={copy}>{copied ? 'Copied' : 'Copy receipt'}</ActionBtn>
            <ActionBtn onClick={() => download(ask, 'csv')}>Download CSV</ActionBtn>
            <ActionBtn onClick={() => download(ask, 'sql')}>Export SQL</ActionBtn>
            <ActionBtn onClick={() => download(ask, 'receipt')}>Export receipt</ActionBtn>
            {savedOk ? (
              <Link to="/saved" className="rounded-full border border-lv-green/50 px-4 py-1.5 text-sm text-lv-green">Saved. Open Saved</Link>
            ) : (
              <ActionBtn onClick={() => setSaveOpen((v) => !v)} accent>Save</ActionBtn>
            )}
          </div>
        )}
        {saveOpen && (
          <div className="-mt-4 mb-7 flex gap-2">
            <input
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              aria-label="Name for the saved answer"
              className="min-w-0 flex-1 rounded-xl border border-line bg-surface-2 px-4 py-2 text-sm text-ink focus:border-brand focus:outline-none"
            />
            <button onClick={save} className="rounded-xl bg-accent px-5 py-2 text-sm font-bold text-on-accent">Save</button>
          </div>
        )}
        {saveError && <p className="-mt-4 mb-7 text-sm text-lv-red">{saveError}</p>}

        {/* lineage */}
        <Section title="Where this number came from">
          {ask.lineage ? (
            <div className="rounded-xl border border-brand/40 bg-brand/10 p-4 font-mono text-sm leading-relaxed">
              <div className="mb-1 text-lg font-bold text-ink">{ask.answer_text ?? ask.lineage.output}</div>
              <LineRow k="=">{ask.lineage.formula}</LineRow>
              <LineRow k="from">{ask.lineage.tables.join(' JOIN ')}</LineRow>
              {ask.lineage.filters.map((f, i) => <LineRow key={f} k={i === 0 ? 'where' : 'and'}>{f}</LineRow>)}
              {ask.lineage.group_by.length > 0 && <LineRow k="by">{ask.lineage.group_by.join(', ')}</LineRow>}
              {ask.lineage.period && <LineRow k="period">{ask.lineage.period}</LineRow>}
              <p className="mt-2 font-sans text-xs text-muted">Read from the SQL, not guessed.</p>
            </div>
          ) : (
            <p className="text-sm text-muted">{ask.sql ? 'The SQL could not be broken down, so only the SQL is shown below.' : 'There is no chosen SQL for this question.'}</p>
          )}
        </Section>

        {/* SQL and result */}
        {hasAnswer && (
          <Section title="SQL used and result">
            <div className="mb-3"><SqlBlock sql={ask.sql!} /></div>
            <ResultTable columns={ask.columns} rows={ask.rows} max={5} />
          </Section>
        )}

        {/* attempts */}
        <Section title={`${ask.n_attempts} attempts`}>
          <div className="mb-4"><AttemptDots ask={ask} /></div>
          <div className="space-y-2">
            {ask.groups.map((g, gi) => (
              <div key={gi} className="rounded-xl border border-line bg-surface-2">
                <button onClick={() => setOpenGroup(openGroup === gi ? null : gi)} className="flex w-full items-center gap-3 px-4 py-3 text-left">
                  <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: GROUP_COLORS[gi % GROUP_COLORS.length] }} />
                  <span className="text-sm font-semibold">Group {groupLetter(gi)}</span>
                  <span className="text-sm text-muted">{g.size} {g.size === 1 ? 'attempt' : 'attempts'}</span>
                  <span className="ml-auto font-mono text-sm font-bold">{g.empty || !g.preview.length ? 'empty' : g.preview[0].map(formatCell).join(', ')}</span>
                  <span className="text-xs text-muted">{openGroup === gi ? 'Hide SQL' : 'Show SQL'}</span>
                </button>
                {openGroup === gi && <div className="px-4 pb-4"><SqlBlock sql={g.sql} /></div>}
              </div>
            ))}
            {ask.n_cannot_answer > 0 && <p className="text-sm text-muted">{ask.n_cannot_answer} of {ask.n_attempts} attempts said this cannot be answered from the data.</p>}
            {ask.n_failed > 0 && <p className="text-sm text-muted">{ask.n_failed} of {ask.n_attempts} attempts failed to run.</p>}
          </div>
        </Section>

        {/* checks */}
        <Section title="Checks">
          <ul className="divide-y divide-line rounded-xl border border-line">
            {ask.checks.map((c) => (
              <li key={c.key} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <span className={`w-16 shrink-0 rounded px-1.5 py-0.5 text-center text-[0.65rem] font-black tracking-wider ${STATUS_STYLE[c.status]}`}>{STATUS_LABEL[c.status]}</span>
                <span className="font-semibold">{c.name}</span>
                <span className="text-muted">{c.detail}</span>
              </li>
            ))}
          </ul>
        </Section>

        {/* knowledge */}
        <Section title="Definitions and approved answers used">
          {ask.knowledge_used.length ? (
            <ul className="space-y-1.5">
              {ask.knowledge_used.map((k) => (
                <li key={k} className="rounded-lg border border-brand/40 bg-brand/10 px-3 py-2 text-sm">{k}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No saved meanings or approved answers were used for this question.</p>
          )}
          {meaningsUsed.length > 0 && (
            <Link to="/metrics" className="mt-2 inline-block text-sm text-brand-text hover:underline">See the definitions on the Metrics page</Link>
          )}
        </Section>

        {/* tested trust */}
        <Section title="Tested trust">
          {ask.tested_trust ? (
            <p className="text-sm">
              When Verdict says {ask.level}, it was right <b>{percent(ask.tested_trust.precision)}</b> of the time in testing
              <span className="text-muted"> ({range(ask.tested_trust.low, ask.tested_trust.high)}), on {ask.tested_trust.on}.</span>
            </p>
          ) : (
            <p className="text-sm text-muted">Waiting for the full evaluation. This line will show how often this level was right in testing, with its range.</p>
          )}
        </Section>

        <p className="mb-6 text-xs text-muted">
          {ask.cache_hit && ask.cached_at && `Answered from cache, first checked at ${formatDate(ask.cached_at)}. `}
          Model: {ask.model_label}. Total time: {seconds(ask.latency_ms)}.
          {ask.elapsed_ms !== undefined && ` Query time: ${seconds(ask.elapsed_ms)}.`}
          {hasAnswer && ` ${ask.row_count.toLocaleString('en-US')} ${ask.row_count === 1 ? 'row' : 'rows'}.`}
        </p>

        {/* event log */}
        <div className="rounded-xl border border-line">
          <button onClick={() => setShowLog((v) => !v)} className="flex w-full items-center justify-between px-4 py-3 text-left text-sm">
            <span className="font-semibold">Event log</span>
            <span className="text-xs text-muted">
              {showLog ? 'Hide' : events ? `Show ${events.length} ${events.length === 1 ? 'event' : 'events'}` : eventsError ? 'Not available' : 'Loading...'}
            </span>
          </button>
          {showLog && (
            <ol className="border-t border-line px-4 py-3">
              {eventsError && <li className="text-sm text-lv-red">{eventsError}</li>}
              {events && events.length === 0 && <li className="text-sm text-muted">No events recorded.</li>}
              {(events ?? []).map((e, i) => (
                <li key={i} className="flex gap-3 py-1.5 text-sm">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${e.actor === 'analyst' ? 'bg-accent' : 'bg-brand-text'}`} />
                  <span className="w-16 shrink-0 text-xs text-muted">{e.actor === 'analyst' ? 'Analyst' : 'Verdict'}</span>
                  <span className="flex-1">
                    {e.action}
                    {e.detail && <span className="text-muted">: {e.detail}</span>}
                  </span>
                  <span className="shrink-0 text-xs text-muted">{timeAgo(e.created_at)}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </aside>
    </div>
  )
}

function ActionBtn({ children, onClick, accent }: { children: ReactNode; onClick: () => void; accent?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-4 py-1.5 text-sm ${accent ? 'bg-accent font-bold text-on-accent' : 'border border-line text-ink hover:border-brand'}`}
    >
      {children}
    </button>
  )
}

function LineRow({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="w-14 shrink-0 text-right text-muted">{k}</span>
      <span className="text-ink">{children}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-7">
      <h3 className="mb-3 text-xs font-extrabold uppercase tracking-[0.14em] text-muted">{title}</h3>
      {children}
    </section>
  )
}
