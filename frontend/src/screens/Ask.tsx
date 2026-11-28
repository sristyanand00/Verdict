// Ask: the main page. The verdict and its reasons come first, the answer and SQL below,
// and the receipt one click away. The analyst can flag a Trusted answer as wrong.

import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { LevelBadge, ReasonChip } from '../components/LevelBadge'
import { DatabasePicker } from '../components/DatabasePicker'
import { Receipt } from '../components/Receipt'
import { Replay, replayOn, setReplay } from '../components/Replay'
import { ResultTable, SqlBlock } from '../components/ResultTable'
import { api, ApiError, notifyChanged } from '../lib/api'
import { useDatabase } from '../lib/database'
import { formatDate, seconds } from '../lib/format'
import { describeError } from '../lib/errors'
import { useSession } from '../lib/session'
import type { AskResponse, Level } from '../lib/types'

// Example questions, only for databases we know. Other databases show none.
const TRY: Record<string, string[]> = {
  olist: [
    'How many orders were canceled?',
    'Which payment type is used most often?',
    'How many orders were delivered late in 2018?',
    'What was our return on ad spend in 2018?',
  ],
}

const HEADLINE: Record<Level, string> = {
  trusted: 'Trusted answer',
  review: 'Needs review',
  reject: 'Rejected',
}

const LEVEL_BORDER: Record<Level, string> = {
  trusted: 'border-lv-green/50',
  review: 'border-lv-yellow/50',
  reject: 'border-lv-red/50',
}

export default function Ask() {
  const [params, setParams] = useSearchParams()
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ title: string; text: string } | null>(null)
  const [noCredits, setNoCredits] = useState<string | null>(null)
  const { me } = useSession()
  const { current: db, databases, choose } = useDatabase()
  const [current, setCurrent] = useState<AskResponse | null>(null)
  const [receipt, setReceipt] = useState(false)
  // a stored answer being shown step by step (recordings only, see Replay.tsx)
  const [replaying, setReplaying] = useState<AskResponse | null>(null)

  const replayParam = params.get('replay')
  useEffect(() => {
    if (replayParam === '1') setReplay(true)
    if (replayParam === '0') setReplay(false)
  }, [replayParam])

  // /ask?id=... opens a past question (from History, Saved or the review queue)
  // /ask?db=...&q=... (from "Ask a similar question") picks that database and fills in the question
  const dbParam = params.get('db')
  const qParam = params.get('q')
  useEffect(() => {
    if (dbParam) choose(dbParam)
    if (qParam) setQuestion(qParam)
  }, [dbParam, qParam, choose])

  const idParam = params.get('id')
  useEffect(() => {
    if (!idParam) return
    api
      .getAsk(idParam)
      .then((a) => {
        setCurrent(a)
        choose(a.database_id)
      }).catch((e) => setError({ title: 'Could not open that question', text: e instanceof Error ? e.message : '' }))
  }, [idParam])

  async function submit(q: string) {
    const text = q.trim()
    if (!text || loading || !db) return
    setQuestion(text)
    setLoading(true)
    setError(null)
    setNoCredits(null)
    setCurrent(null)
    setReplaying(null)
    if (idParam || dbParam || qParam) setParams({}, { replace: true })
    try {
      const res = await api.ask(text, db.id)
      if (res.cache_hit && replayOn()) setReplaying(res)
      else setCurrent(res)
      notifyChanged()
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) setNoCredits(e.message)
      else setError(describeError(e))
      notifyChanged()
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    submit(question)
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="min-w-0">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="mb-1 text-3xl font-bold">Ask</h1>
            <p className="text-muted">Ask in plain English. Verdict writes the SQL 8 times, checks the answers and tells you whether to trust them.</p>
          </div>
        </div>
        <div className="mb-3">
          <DatabasePicker disabled={loading} />
        </div>

        {/* question box */}
        <form onSubmit={onSubmit} className="mb-3 flex gap-3 rounded-2xl border border-brand/40 bg-surface p-3 focus-within:border-brand">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="How many orders were canceled?"
            aria-label="Your question"
            className="min-w-0 flex-1 bg-transparent px-3 text-lg text-ink placeholder:text-muted/60 focus:outline-none"
          />
          <button type="submit" disabled={loading || !!replaying || !question.trim() || !db} className="rounded-xl bg-brand px-7 py-3 font-bold text-on-brand disabled:opacity-50">
            {loading || replaying ? 'Checking...' : 'Ask'}
          </button>
        </form>
        {me && me.user.role === 'admin' && <p className="mb-3 text-xs text-muted">Your own questions are free (provider account).</p>}
        {me && me.user.role !== 'admin' && (
          <p className={`mb-3 text-xs ${me.credits.balance < me.prices.ask ? 'text-lv-yellow' : 'text-muted'}`}>
            Each question uses {me.prices.ask} {me.prices.ask === 1 ? 'credit' : 'credits'}. You have {me.credits.balance.toLocaleString('en-US')} left.{' '}
            <Link to="/account" className="text-brand-text hover:underline">See usage</Link>
          </p>
        )}
        {db && TRY[db.id] && (
        <div className="mb-8 flex flex-wrap items-center gap-2 text-xs text-muted">
          Try:
          {TRY[db.id].map((t) => (
            <button key={t} onClick={() => submit(t)} disabled={loading} className="rounded-full border border-line bg-surface-2 px-3 py-1 text-ink hover:border-brand disabled:opacity-50">
              {t}
            </button>
          ))}
        </div>
        )}
        {databases && !db && <p className="mb-8 text-sm text-muted">Pick a database to ask a question.</p>}

        {loading && <Loading question={question} />}
        {replaying && !loading && (
          <Replay ask={replaying} onDone={() => { setCurrent(replaying); setReplaying(null) }} />
        )}
        {noCredits && (
          <div className="rounded-2xl border border-lv-yellow/50 bg-lv-yellow-tint p-5">
            <div className="mb-1 font-bold text-lv-yellow">No credits left</div>
            <p className="text-sm text-ink">
              {noCredits}{' '}
              <Link to="/account" className="text-brand-text hover:underline">See your usage</Link>
            </p>
          </div>
        )}
        {error && (
          <div className="rounded-2xl border border-lv-red/50 bg-lv-red-tint p-5">
            <div className="mb-1 font-bold text-lv-red">{error.title}</div>
            <p className="text-sm text-ink">{error.text}</p>
          </div>
        )}
        {current && !loading && <VerdictCard key={current.ask_id} ask={current} onReceipt={() => setReceipt(true)} />}
        {!current && !replaying && !loading && !error && !noCredits && (
          <div className="rounded-2xl border border-dashed border-line p-10 text-center text-muted">
            Your answer will appear here, with its verdict first.
          </div>
        )}
      </div>

      {receipt && current && <Receipt ask={current} onClose={() => setReceipt(false)} />}
    </div>
  )
}

function Loading({ question }: { question: string }) {
  return (
    <div className="rounded-2xl border border-brand/40 bg-surface p-6">
      <div className="mb-4 text-sm text-muted">"{question}"</div>
      <div className="flex items-center gap-3">
        <svg viewBox="0 0 24 24" className="anim-spin h-5 w-5" fill="none" stroke="var(--color-accent)" strokeWidth={2.5}>
          <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
        </svg>
        <span className="font-semibold">Checking your question</span>
      </div>
      <p className="mt-2 text-sm text-muted">
        Writing 8 SQL attempts, running each one safely, comparing the results and running the checks. On a laptop this can take a minute.
      </p>
    </div>
  )
}

function VerdictCard({ ask, onReceipt }: { ask: AskResponse; onReceipt: () => void }) {
  const [chosen, setChosen] = useState<number | null>(null)
  const [approved, setApproved] = useState(false)
  const [meaningTerm, setMeaningTerm] = useState('')
  const [flagOpen, setFlagOpen] = useState(false)
  const [flagNote, setFlagNote] = useState('')
  const [flagged, setFlagged] = useState(ask.flagged)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function flag() {
    setBusy(true)
    try {
      await api.flagAsk(ask.ask_id, flagNote)
      setFlagged(true)
      setFlagOpen(false)
      notifyChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not flag it')
    } finally {
      setBusy(false)
    }
  }

  async function approveChoice() {
    if (chosen === null || !ask.options) return
    setBusy(true)
    setErr(null)
    try {
      const term = meaningTerm.trim()
      await api.chooseOption(ask.ask_id, chosen, term ? { term, definition: ask.options[chosen].label } : undefined)
      setApproved(true)
      notifyChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not save the choice')
    } finally {
      setBusy(false)
    }
  }

  const option = chosen !== null && ask.options ? ask.options[chosen] : null
  const showAnswer = option !== null || ask.answer_text !== null

  return (
    <div className={`anim-pop rounded-3xl border bg-surface ${LEVEL_BORDER[ask.level]}`}>
      {/* verdict and reasons first */}
      <div className="border-b border-line p-6">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <span className="anim-stamp"><LevelBadge level={ask.level} big /></span>
          <span className="text-xl font-bold">{HEADLINE[ask.level]}</span>
          <span className="ml-auto text-sm text-muted">"{ask.question}"</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {ask.reasons.map((r) => <ReasonChip key={r.code + r.text}>{r.text}</ReasonChip>)}
        </div>
        {ask.level === 'review' && !ask.options && (
          <p className="mt-4 text-sm text-muted">Not sure enough to call this Trusted. The draft below is unverified until it is approved in the review queue.</p>
        )}
      </div>

      {/* two meanings: pick one */}
      {ask.options && (
        <div className="border-b border-line p-6">
          <p className="mb-3 text-sm">This question can mean two things. Pick the one you meant:</p>
          <div className="grid gap-3 md:grid-cols-2">
            {ask.options.map((o, i) => (
              <button
                key={o.label}
                onClick={() => !approved && setChosen(i)}
                disabled={approved}
                className={`rounded-2xl border p-4 text-left transition-colors ${chosen === i ? 'border-brand bg-brand/15' : 'border-line bg-surface-2 hover:border-brand/60'}`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-lv-violet-tint text-xs font-black text-lv-violet">{String.fromCharCode(65 + i)}</span>
                  <span className="font-semibold">{o.label}</span>
                </div>
                <div className="font-mono text-2xl font-bold">{o.answer_text}</div>
                <div className="mt-1 text-xs text-muted">{o.size} of {ask.n_attempts} attempts chose this</div>
              </button>
            ))}
          </div>
          {option && !approved && (
            <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface-2 p-4">
              <span className="text-sm">Approve "{option.label}" as the right reading?</span>
              <input
                value={meaningTerm}
                onChange={(e) => setMeaningTerm(e.target.value)}
                placeholder='Save as a meaning, e.g. "revenue" (optional)'
                className="min-w-[16rem] flex-1 rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-brand focus:outline-none"
              />
              <button onClick={approveChoice} disabled={busy} className="rounded-xl bg-accent px-5 py-2 text-sm font-bold text-on-accent disabled:opacity-50">
                Approve this reading
              </button>
            </div>
          )}
          {approved && option && (
            <p className="mt-4 text-sm text-lv-green">
              Approved "{option.label}". Saved as an approved answer{meaningTerm.trim() ? ` and as the meaning of "${meaningTerm.trim()}"` : ''}.
            </p>
          )}
        </div>
      )}

      {/* not in the data */}
      {ask.level === 'reject' && ask.reasons.some((r) => r.code === 'not_in_data') && (
        <div className="border-b border-line p-6">
          <p className="mb-2">{ask.missing ? <>Your data does not contain <b>{ask.missing}</b>.</> : 'Your data does not seem to contain what this question needs.'}</p>
          {ask.tables_available && <p className="text-sm text-muted">Tables available: {ask.tables_available.join(', ')}.</p>}
          <p className="mt-2 text-sm text-muted">{ask.n_cannot_answer} of {ask.n_attempts} attempts said this cannot be answered.</p>
        </div>
      )}

      {/* answer and SQL */}
      {showAnswer && (
        <div className="grid gap-6 p-6 lg:grid-cols-2">
          <div className="min-w-0">
            <div className="mb-2 text-xs font-extrabold uppercase tracking-[0.14em] text-muted">
              Answer{option ? `: ${option.label}` : ''}
              {ask.level !== 'trusted' && !approved && ' (unverified)'}
              {approved && ' (approved by you)'}
            </div>
            <div className="mb-4 font-mono text-4xl font-bold">{option ? option.answer_text : ask.answer_text}</div>
            <ResultTable columns={option ? option.columns : ask.columns} rows={option ? option.rows : ask.rows} />
          </div>
          <div className="min-w-0">
            <div className="mb-2 text-xs font-extrabold uppercase tracking-[0.14em] text-muted">SQL used</div>
            <SqlBlock sql={(option ? option.sql : ask.sql) ?? ''} />
          </div>
        </div>
      )}

      {/* actions */}
      <div className="flex flex-wrap items-center gap-3 border-t border-line p-5">
        <button onClick={onReceipt} className="rounded-full bg-brand px-5 py-2 text-sm font-bold text-on-brand">
          Open the receipt
        </button>

        {ask.level === 'trusted' && !flagged && (
          <button onClick={() => setFlagOpen((v) => !v)} className="rounded-full border border-line px-5 py-2 text-sm text-ink hover:border-lv-red">
            Flag as wrong
          </button>
        )}
        {ask.level !== 'trusted' && !approved && (
          <span className="text-sm text-muted">
            This question is in the review queue.{' '}
            {ask.review_id && <Link to={`/review/${ask.review_id}`} className="text-brand-text hover:underline">Open it</Link>}
          </span>
        )}
        {flagged && <span className="text-sm text-lv-yellow">Flagged. It is now in the review queue.</span>}
        {err && <span className="text-sm text-lv-red">{err}</span>}

        <span className="ml-auto text-xs text-muted">
          {ask.cache_hit && ask.cached_at ? `Answered from cache, first checked at ${formatDate(ask.cached_at)}. ` : ''}
          {ask.cache_stale ? 'The model is not reachable now, so this is the answer from before the last knowledge change. ' : ''}
          {ask.model_label}, {seconds(ask.latency_ms)}
        </span>
      </div>

      {flagOpen && (
        <div className="border-t border-line p-5">
          <label className="mb-2 block text-sm">What looks wrong? (optional)</label>
          <div className="flex gap-3">
            <input
              value={flagNote}
              onChange={(e) => setFlagNote(e.target.value)}
              placeholder="For example: this should exclude cancelled orders"
              className="min-w-0 flex-1 rounded-xl border border-line bg-surface-2 px-4 py-2 text-sm text-ink focus:border-brand focus:outline-none"
            />
            <button onClick={flag} disabled={busy} className="rounded-xl bg-lv-red px-5 py-2 text-sm font-bold text-bg disabled:opacity-50">
              Flag it
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

