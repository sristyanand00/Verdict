// One review item. The analyst sees why it was not Trusted and the attempt groups,
// edits and re-runs the SQL (same read-only verifier), then approves, fixes or rejects.
// Approvals become approved examples; optionally a meaning or a known number too.

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { LevelBadge, ReasonChip } from '../components/LevelBadge'
import { AttemptDots, Receipt } from '../components/Receipt'
import { GROUP_COLORS, groupLetter } from '../lib/groups'
import { ResultTable } from '../components/ResultTable'
import { api, notifyChanged } from '../lib/api'
import { formatCell, seconds, timeAgo } from '../lib/format'
import type { ResolveBody, ReviewDetail as Detail, SqlRunResult } from '../lib/types'

export default function ReviewDetail() {
  const { id = '' } = useParams()
  const [item, setItem] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [sql, setSql] = useState('')
  const [run, setRun] = useState<SqlRunResult | null>(null)
  const [running, setRunning] = useState(false)
  const [ranSql, setRanSql] = useState<string | null>(null)

  const [knownOn, setKnownOn] = useState(false)
  const [knownName, setKnownName] = useState('')
  const [meaningOn, setMeaningOn] = useState(false)
  const [term, setTerm] = useState('')
  const [definition, setDefinition] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionErr, setActionErr] = useState<string | null>(null)
  const [receipt, setReceipt] = useState(false)

  useEffect(() => {
    api
      .reviewGet(id)
      .then((d) => {
        setItem(d)
        const start = d.final_sql ?? d.ask.sql ?? d.ask.groups[0]?.sql ?? ''
        setSql(start)
        setKnownName(d.ask.question.replace(/\?$/, ''))
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load this item'))
  }, [id])

  if (error) return <p className="rounded-xl border border-lv-red/50 bg-lv-red-tint p-4 text-sm">{error}</p>
  if (!item) return <p className="text-muted">Loading...</p>

  const ask = item.ask
  const draft = ask.sql ?? ''
  const edited = sql.trim() !== draft.trim()
  const fixReady = edited && run?.status === 'ok' && ranSql === sql
  const open = item.status === 'open'

  async function runIt() {
    setRunning(true)
    try {
      const r = await api.runSql(sql, ask.database_id)
      setRun(r)
      setRanSql(sql)
    } catch (e) {
      setRun({ status: 'error', columns: [], rows: [], row_count: 0, truncated: false, error: e instanceof Error ? e.message : 'Failed', elapsed_ms: 0 })
    } finally {
      setRunning(false)
    }
  }

  async function resolve(action: ResolveBody['action']) {
    setBusy(true)
    setActionErr(null)
    const body: ResolveBody = { action }
    if (note.trim()) body.note = note.trim()
    if (action === 'fix') body.sql = sql
    if (action !== 'reject') {
      if (meaningOn && term.trim() && definition.trim()) body.save_meaning = { term: term.trim(), definition: definition.trim() }
      if (knownOn && knownName.trim()) body.save_known_number = { name: knownName.trim() }
    }
    try {
      setItem(await api.resolve(item!.review_id, body))
      notifyChanged()
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : 'Could not save this')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-[96rem]">
      <Link to="/review" className="mb-4 inline-block text-sm text-muted hover:text-ink">&larr; Back to the review queue</Link>

      <div className="mb-6 rounded-2xl border border-line bg-surface p-6">
        <div className="mb-3 flex flex-wrap items-center gap-4">
          <LevelBadge level={ask.level} big />
          <h1 className="text-2xl font-bold">{ask.question}</h1>
          <span className="ml-auto text-xs text-muted">Asked {timeAgo(ask.created_at)}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {item.source === 'flagged' && <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-bold text-on-accent">Flagged by you{ask.flag_note ? `: ${ask.flag_note}` : ''}</span>}
          <span className="mr-1 text-sm text-muted">{item.source === 'flagged' ? 'Verdict said Trusted because:' : 'Why not Trusted:'}</span>
          {ask.reasons.map((r) => <ReasonChip key={r.code + r.text}>{r.text}</ReasonChip>)}
        </div>
      </div>

      {!open && <Resolved item={item} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,26rem)_1fr]">
        {/* left: attempt groups */}
        <div className="min-w-0 space-y-4">
          <div className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="mb-3 text-xs font-extrabold uppercase tracking-[0.14em] text-muted">{ask.n_attempts} attempts</h2>
            <div className="mb-4"><AttemptDots ask={ask} /></div>
            <p className="mb-2 text-xs text-muted">Click a group to load its SQL into the editor.</p>
            <div className="space-y-2">
              {ask.groups.map((g, gi) => (
                <button
                  key={gi}
                  disabled={!open}
                  onClick={() => {
                    setSql(g.sql)
                    setRun(null)
                  }}
                  className={`flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left ${sql.trim() === g.sql.trim() ? 'border-brand bg-brand/10' : 'border-line bg-surface-2 hover:border-brand/60'}`}
                >
                  <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: GROUP_COLORS[gi % GROUP_COLORS.length] }} />
                  <span className="text-sm font-semibold">Group {groupLetter(gi)}</span>
                  <span className="text-sm text-muted">{g.size} of {ask.n_attempts}</span>
                  <span className="ml-auto font-mono text-sm font-bold">{g.empty || !g.preview.length ? 'empty' : g.preview[0].map(formatCell).join(', ')}</span>
                </button>
              ))}
              {ask.n_cannot_answer > 0 && <p className="text-sm text-muted">{ask.n_cannot_answer} said it cannot be answered.</p>}
              {ask.n_failed > 0 && <p className="text-sm text-muted">{ask.n_failed} failed to run.</p>}
            </div>
          </div>

          {ask.options && (
            <div className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="mb-3 text-xs font-extrabold uppercase tracking-[0.14em] text-muted">Two meanings</h2>
              {ask.options.map((o, i) => (
                <button key={o.label} disabled={!open} onClick={() => { setSql(o.sql); setRun(null) }} className="mb-2 flex w-full items-center gap-3 rounded-xl border border-line bg-surface-2 px-4 py-3 text-left hover:border-brand/60">
                  <span className="grid h-6 w-6 place-items-center rounded-full bg-lv-violet-tint text-xs font-black text-lv-violet">{groupLetter(i)}</span>
                  <span className="text-sm font-semibold">{o.label}</span>
                  <span className="ml-auto font-mono text-sm font-bold">{o.answer_text}</span>
                </button>
              ))}
            </div>
          )}

          <button onClick={() => setReceipt(true)} className="w-full rounded-xl border border-line px-4 py-2.5 text-sm text-ink hover:border-brand">
            Open the full receipt (checks, lineage, event log)
          </button>
        </div>

        {/* right: SQL editor and result */}
        <div className="min-w-0 space-y-4">
          <div className="rounded-2xl border border-line bg-surface p-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-xs font-extrabold uppercase tracking-[0.14em] text-muted">
                SQL {open ? '(you can edit it)' : ''}
                {edited && open && <span className="ml-2 rounded bg-accent px-1.5 py-0.5 text-[0.65rem] text-on-accent">EDITED</span>}
              </h2>
              {open && edited && draft && (
                <button onClick={() => { setSql(draft); setRun(null) }} className="text-xs text-muted hover:text-ink">Reset to the draft</button>
              )}
            </div>
            <textarea
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              readOnly={!open}
              spellCheck={false}
              aria-label="SQL"
              rows={Math.min(16, Math.max(6, sql.split('\n').length + 1))}
              className="w-full resize-y rounded-xl border border-line bg-bg p-4 font-mono text-sm leading-relaxed text-ink focus:border-brand focus:outline-none"
            />
            <div className="mt-3 flex items-center gap-3">
              <button onClick={runIt} disabled={running || !sql.trim()} className="rounded-xl bg-brand px-6 py-2 text-sm font-bold text-on-brand disabled:opacity-50">
                {running ? 'Running...' : 'Run'}
              </button>
              <span className="text-xs text-muted">Runs read-only through the same safe verifier as every attempt.</span>
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="mb-3 text-xs font-extrabold uppercase tracking-[0.14em] text-muted">Result</h2>
            {!run && !ask.rows.length && <p className="text-sm text-muted">Press Run to see the result.</p>}
            {!run && ask.rows.length > 0 && (
              <>
                <p className="mb-2 text-sm text-muted">Draft result (unverified):</p>
                <ResultTable columns={ask.columns} rows={ask.rows} />
              </>
            )}
            {run && run.status !== 'ok' && (
              <div className="rounded-xl border border-lv-red/50 bg-lv-red-tint p-4 text-sm">
                <b className="text-lv-red">{run.status === 'blocked' ? 'Blocked' : 'Did not run'}</b>: {run.error}
              </div>
            )}
            {run && run.status === 'ok' && (
              <>
                <ResultTable columns={run.columns} rows={run.rows} />
                <p className="mt-2 text-xs text-muted">
                  {run.row_count.toLocaleString('en-US')} {run.row_count === 1 ? 'row' : 'rows'}{run.truncated && ' (cut off)'}, {seconds(run.elapsed_ms)}
                </p>
              </>
            )}
          </div>
        </div>
      </div>

      {/* decision */}
      {open && (
        <div className="mt-6 rounded-2xl border border-brand/40 bg-surface p-6">
          <h2 className="mb-4 text-lg font-bold">Your decision</h2>
          <div className="mb-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-line bg-surface-2 p-4">
              <label className="flex items-center gap-2 text-sm font-semibold">
                <input type="checkbox" checked={meaningOn} onChange={(e) => setMeaningOn(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />
                Save a meaning
              </label>
              <p className="mt-1 mb-2 text-xs text-muted">Teaches Verdict what a word means here. Used on future questions.</p>
              {meaningOn && (
                <div className="flex flex-wrap gap-2">
                  <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Word, e.g. late order" className="w-40 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm focus:border-brand focus:outline-none" />
                  <input value={definition} onChange={(e) => setDefinition(e.target.value)} placeholder="Meaning, e.g. delivered after the estimated date" className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm focus:border-brand focus:outline-none" />
                </div>
              )}
            </div>
            <div className="rounded-xl border border-line bg-surface-2 p-4">
              <label className="flex items-center gap-2 text-sm font-semibold">
                <input type="checkbox" checked={knownOn} onChange={(e) => setKnownOn(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />
                Save as a known number
              </label>
              <p className="mt-1 mb-2 text-xs text-muted">Later answers that disagree with it go to review.</p>
              {knownOn && (
                <input value={knownName} onChange={(e) => setKnownName(e.target.value)} placeholder="Name" className="w-full rounded-lg border border-line bg-surface px-3 py-1.5 text-sm focus:border-brand focus:outline-none" />
              )}
            </div>
          </div>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional). For a reject, say why."
            className="mb-4 w-full rounded-xl border border-line bg-surface-2 px-4 py-2 text-sm focus:border-brand focus:outline-none"
          />
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => resolve('approve')}
              disabled={busy || !draft || edited}
              title={edited ? 'You changed the SQL. Use "Approve my fix" instead.' : !draft ? 'There is no draft. Write a fix and run it.' : ''}
              className="rounded-xl bg-lv-green px-5 py-2.5 text-sm font-bold text-bg disabled:opacity-40"
            >
              Approve the draft
            </button>
            <button
              onClick={() => resolve('fix')}
              disabled={busy || !fixReady}
              title={!edited ? 'Edit the SQL first' : !fixReady ? 'Run your SQL first' : ''}
              className="rounded-xl bg-accent px-5 py-2.5 text-sm font-bold text-on-accent disabled:opacity-40"
            >
              Approve my fix
            </button>
            <button onClick={() => resolve('reject')} disabled={busy} className="rounded-xl border border-lv-red/60 px-5 py-2.5 text-sm font-bold text-lv-red disabled:opacity-40">
              Reject
            </button>
            {edited && !fixReady && <span className="text-xs text-muted">Run your edited SQL before approving it.</span>}
            {actionErr && <span className="text-sm text-lv-red">{actionErr}</span>}
          </div>
        </div>
      )}

      {receipt && <Receipt ask={ask} onClose={() => setReceipt(false)} />}
    </div>
  )
}

function Resolved({ item }: { item: Detail }) {
  const ok = item.status !== 'rejected'
  return (
    <div className={`anim-pop mb-6 rounded-2xl border p-5 ${ok ? 'border-lv-green/50 bg-lv-green-tint' : 'border-lv-red/50 bg-lv-red-tint'}`}>
      <div className={`mb-1 font-bold ${ok ? 'text-lv-green' : 'text-lv-red'}`}>
        {item.status === 'approved' && 'Approved'}
        {item.status === 'fixed' && 'Fixed and approved'}
        {item.status === 'rejected' && 'Rejected'}
        {item.resolved_at && <span className="font-normal text-muted"> {timeAgo(item.resolved_at)}</span>}
      </div>
      {ok ? (
        <p className="text-sm text-ink">
          Saved as an approved answer{item.final_rows?.[0] ? <> ({item.final_rows[0].map(formatCell).join(', ')})</> : null}. Verdict will use it for similar questions, and the checks still decide the level.{' '}
          <Link to={`/ask?db=${encodeURIComponent(item.ask.database_id)}&q=${encodeURIComponent(item.ask.question)}`} className="text-brand-text hover:underline">Ask a similar question</Link>
        </p>
      ) : (
        <p className="text-sm text-ink">{item.note ?? 'No reason given.'}</p>
      )}
    </div>
  )
}
