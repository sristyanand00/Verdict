// Model Arena: the user's own model and outside models (Gemini and others) answer the same question.
// Every answer goes through the same verifier and trust rules as Ask (POST /api/arena/run).
// One model failing or being off never hides the others. Arena runs are not saved as asks.
// Saved runs of scripted questions come from GET /api/arena and /api/arena/{key}.
// Below, the scoreboard from the full evaluation (GET /api/arena/models); a missing number stays missing.

import { useEffect, useState, type FormEvent } from 'react'
import { LevelBadge, ReasonChip } from '../components/LevelBadge'
import { ResultTable, SqlBlock } from '../components/ResultTable'
import { Robot, type RobotKind, type RobotMood } from '../components/Robot'
import { api, notifyChanged } from '../lib/api'
import { useDatabase } from '../lib/database'
import { DatabasePicker } from '../components/DatabasePicker'
import { describeError } from '../lib/errors'
import { formatDate, seconds } from '../lib/format'
import { useSession } from '../lib/session'
import type { ArenaRunResponse, ArenaRunResult, ArenaScore, ModelInfo } from '../lib/types'

const MAX_MODELS = 4

// Example questions, only for databases we know. Other databases show none.
const TRY: Record<string, string[]> = {
  olist: ['How many orders were delivered late in 2018?', 'What was our revenue in 2017?', 'Which product category sold the most items in 2017?'],
}

// GET /api/arena/{key} is not described field by field in docs/API.md. This page shows it only
// when it has the same shape as a live run (a "results" list); anything else is reported, not guessed.
function asRun(x: unknown): { question?: string; results: ArenaRunResult[] } | null {
  if (!x || typeof x !== 'object') return null
  const r = (x as { results?: unknown }).results
  if (!Array.isArray(r) || !r.every((i) => i && typeof i === 'object' && 'model_id' in i && 'status' in i)) return null
  return x as { question?: string; results: ArenaRunResult[] }
}

function robotKind(m: { model_id?: string; id?: string; kind: ModelInfo['kind'] }): RobotKind {
  if (m.kind === 'outside') return 'cloud'
  return (m.model_id ?? m.id ?? '').includes('base') ? 'base' : 'grpo'
}

function mood(r: ArenaRunResult | undefined, running: boolean): RobotMood {
  if (running) return 'thinking'
  if (!r || r.status !== 'ok') return 'idle'
  if (r.level === 'trusted') return 'correct'
  if (r.level === 'reject') return 'wrong'
  return 'idle'
}

export default function Arena() {
  const { me } = useSession()
  const { current: db } = useDatabase()
  const [keys, setKeys] = useState<string[] | null>(null)
  const [cached, setCached] = useState<{ key: string; data: unknown } | null>(null)
  const [cachedError, setCachedError] = useState<string | null>(null)
  const [models, setModels] = useState<ModelInfo[] | null>(null)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [picked, setPicked] = useState<string[]>([])
  const [question, setQuestion] = useState('')
  const [running, setRunning] = useState(false)
  const [runModels, setRunModels] = useState<ModelInfo[]>([])
  const [run, setRun] = useState<ArenaRunResponse | null>(null)
  const [error, setError] = useState<{ title: string; text: string } | null>(null)
  const [scores, setScores] = useState<ArenaScore[] | null>(null)
  const [scoresError, setScoresError] = useState<string | null>(null)

  useEffect(() => {
    api
      .models()
      .then((list) => {
        setModels(list)
        // start with every own model and the first outside model, up to the limit
        const own = list.filter((m) => m.kind === 'own').map((m) => m.id)
        const outside = list.filter((m) => m.kind === 'outside').map((m) => m.id)
        setPicked([...own, ...outside.slice(0, 1)].slice(0, MAX_MODELS))
      })
      .catch((e) => setModelsError(e instanceof Error ? e.message : 'Could not load the models'))
    api
      .arenaKeys()
      .then(setKeys)
      .catch(() => setKeys([]))
    api
      .arenaScores()
      .then(setScores)
      .catch((e) => setScoresError(e instanceof Error ? e.message : 'Could not load the scoreboard'))
  }, [])

  const isAdmin = me?.user.role === 'admin'
  const price = me?.prices.arena_outside_model ?? 0
  const outsidePicked = (models ?? []).filter((m) => picked.includes(m.id) && m.kind === 'outside').length
  const cost = isAdmin ? 0 : outsidePicked * price
  const cannotPay = !!me && !isAdmin && cost > me.credits.balance

  function toggle(id: string) {
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length >= MAX_MODELS ? p : [...p, id]))
  }

  async function start(q: string) {
    const text = q.trim()
    if (!text || running || picked.length === 0 || !db) return
    setQuestion(text)
    setRunning(true)
    setError(null)
    setRun(null)
    setCached(null)
    setRunModels((models ?? []).filter((m) => picked.includes(m.id)))
    try {
      setRun(await api.arenaRun(text, picked, db.id))
    } catch (e) {
      setError(describeError(e, 'Could not run the Arena'))
    } finally {
      setRunning(false)
      notifyChanged()
    }
  }

  async function openCached(key: string) {
    setCachedError(null)
    setRun(null)
    setError(null)
    try {
      setCached({ key, data: await api.arenaCached(key) })
    } catch (e) {
      setCachedError(e instanceof Error ? e.message : 'Could not open that saved run')
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void start(question)
  }

  const columns = run ? run.results : runModels.map((m) => ({ model_id: m.id, label: m.label, kind: m.kind }))
  const cacheHits = run?.results.filter((r) => r.cache_hit).length ?? 0

  return (
    <div className="max-w-[90rem]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Model Arena</h1>
          <p className="mt-1 max-w-[48rem] text-sm text-muted">
            Your model and outside models answer the same question on the same data. Each answer goes through the same checks as Ask, so you can
            compare their verdicts side by side. Arena runs are not saved and do not go to the review queue.
          </p>
        </div>
      </div>

      {/* question and models */}
      <form onSubmit={onSubmit} className="mt-8">
        <div className="mb-3">
          <DatabasePicker disabled={running} />
        </div>
        <div className="flex gap-3">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="How many orders were delivered late in 2018?"
            aria-label="Question for the Arena"
            className="min-w-0 flex-1 rounded-md border border-line bg-surface px-4 py-2.5 text-ink placeholder:text-muted/60 focus:border-brand focus:outline-none"
          />
          <button
            type="submit"
            disabled={running || !question.trim() || picked.length === 0 || cannotPay || !db}
            className="rounded-md bg-brand px-6 py-2.5 text-sm font-semibold text-on-brand disabled:opacity-50"
          >
            {running ? 'Running...' : `Run ${picked.length} ${picked.length === 1 ? 'model' : 'models'}`}
          </button>
        </div>
        {db && TRY[db.id] && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          Try:
          {TRY[db.id].map((t) => (
            <button key={t} type="button" onClick={() => void start(t)} disabled={running || cannotPay} className="text-ink/80 hover:text-ink hover:underline disabled:opacity-50">
              {t}
            </button>
          ))}
        </div>
        )}

        <fieldset className="mt-6">
          <legend className="text-xs text-muted">Models (up to {MAX_MODELS})</legend>
          {modelsError && <p className="mt-2 text-sm text-lv-red">{modelsError}</p>}
          {!models && !modelsError && <p className="mt-2 text-sm text-muted">Loading models...</p>}
          {models && models.length === 0 && <p className="mt-2 text-sm text-muted">The server lists no models.</p>}
          <div className="mt-2 flex flex-wrap gap-2">
            {(models ?? []).map((m) => {
              const on = picked.includes(m.id)
              const full = !on && picked.length >= MAX_MODELS
              return (
                <label
                  key={m.id}
                  className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm ${on ? 'border-brand bg-brand/10 text-ink' : 'border-line text-muted'} ${full ? 'cursor-not-allowed opacity-50' : ''}`}
                >
                  <input type="checkbox" checked={on} disabled={running || full} onChange={() => toggle(m.id)} className="accent-[var(--color-brand)]" />
                  <span>{m.label}</span>
                  <span className="text-xs text-muted">
                    {m.kind === 'own' ? 'your model, free' : isAdmin ? 'outside' : `outside, ${price} ${price === 1 ? 'credit' : 'credits'}`}
                  </span>
                  {!m.reachable && <span className="text-xs text-lv-yellow">not reachable</span>}
                </label>
              )
            })}
          </div>
        </fieldset>

        {me && (
          <p className={`mt-3 text-xs ${cannotPay ? 'text-lv-yellow' : 'text-muted'}`}>
            {isAdmin
              ? 'Provider account: Arena runs are free.'
              : cost === 0
                ? 'This run is free: only your own model is picked.'
                : `This run costs up to ${cost} ${cost === 1 ? 'credit' : 'credits'}. You have ${me.credits.balance}. A model that fails or answers from the cache is not charged.`}
            {cannotPay && ' Not enough credits: pick fewer outside models, or ask your provider for more.'}
          </p>
        )}
      </form>

      {/* results */}
      {error && (
        <div className="mt-8 rounded-md border border-lv-red/50 bg-lv-red-tint p-4">
          <div className="font-semibold text-lv-red">{error.title}</div>
          <p className="mt-1 text-sm text-ink">{error.text}</p>
        </div>
      )}

      {running && <p className="mt-8 text-sm text-muted">Each model writes 8 attempts and every one is checked. This can take a minute.</p>}

      {columns.length > 0 && !error && (
        <div className={`mt-6 grid grid-cols-1 gap-6 ${columns.length >= 3 ? 'lg:grid-cols-3' : columns.length === 2 ? 'md:grid-cols-2' : ''} ${columns.length === 4 ? 'xl:grid-cols-4' : ''}`}>
          {columns.map((c) => {
            const r = run?.results.find((x) => x.model_id === c.model_id)
            return <ModelColumn key={c.model_id} label={c.label} kind={c.kind} robot={robotKind(c)} result={r} running={running} />
          })}
        </div>
      )}

      {run && (
        <p className="mt-4 text-xs text-muted">
          {run.credits_charged > 0 ? `This run used ${run.credits_charged} ${run.credits_charged === 1 ? 'credit' : 'credits'}.` : 'This run used no credits.'}
          {cacheHits > 0 && ` ${cacheHits} ${cacheHits === 1 ? 'answer came' : 'answers came'} from the cache.`} One question shows how the models behave, not which is better.
          The scoreboard below is what counts.
        </p>
      )}

      {/* saved runs of scripted questions */}
      {keys && keys.length > 0 && (
        <section className="mt-12">
          <h2 className="text-base font-semibold">Saved runs</h2>
          <p className="mt-1 text-sm text-muted">Earlier runs of fixed questions, kept on the server. Opening one is free.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {keys.map((k) => (
              <button
                key={k}
                onClick={() => void openCached(k)}
                className={`rounded-md border px-3 py-1.5 text-sm ${cached?.key === k ? 'border-brand text-ink' : 'border-line text-muted hover:text-ink'}`}
              >
                {k.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
          {cachedError && <p className="mt-3 text-sm text-lv-red">{cachedError}</p>}
          {cached && <CachedRun data={cached.data} />}
        </section>
      )}

      {/* scoreboard */}
      <section className="mt-14">
        <h2 className="text-base font-semibold">Scoreboard</h2>
        <p className="mt-1 text-sm text-muted">Accuracy on a full benchmark, from the evaluation results. A model with no result says so.</p>
        {scoresError && <p className="mt-3 text-sm text-lv-red">{scoresError}</p>}
        {!scores && !scoresError && <p className="mt-3 text-sm text-muted">Loading...</p>}
        {scores && scores.length === 0 && <p className="mt-3 text-sm text-muted">Not measured yet.</p>}
        {scores && scores.length > 0 && (
          <table className="mt-4 w-full max-w-[56rem] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th className="py-2 pr-4 font-medium">Model</th>
                <th className="py-2 pr-4 font-medium">Benchmark</th>
                <th className="py-2 pr-4 text-right font-medium">Questions</th>
                <th className="py-2 pr-4 text-right font-medium">Accuracy</th>
                <th className="py-2 font-medium">Measured</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((s) => (
                <tr key={`${s.model_id}-${s.benchmark}`} className="border-b border-line/60">
                  <td className="py-2.5 pr-4">
                    <span className="text-ink">{s.label}</span>
                    <span className="ml-2 text-xs text-muted">{s.kind === 'own' ? 'your model' : 'outside'}</span>
                  </td>
                  <td className="py-2.5 pr-4 text-muted">{s.benchmark}</td>
                  <td className="py-2.5 pr-4 text-right font-mono tabular-nums text-muted">{s.n_questions.toLocaleString('en-US')}</td>
                  <td className="py-2.5 pr-4 text-right font-mono tabular-nums">
                    {s.accuracy === null ? <span className="font-sans text-muted">Not measured yet</span> : <span className="text-ink">{(s.accuracy * 100).toFixed(1)}%</span>}
                  </td>
                  <td className="py-2.5 text-muted">{s.measured_at ? formatDate(s.measured_at) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

function ModelColumn({
  label,
  kind,
  robot,
  result,
  running,
}: {
  label: string
  kind: ModelInfo['kind']
  robot: RobotKind
  result: ArenaRunResult | undefined
  running: boolean
}) {
  return (
    <div className="flex min-w-0 flex-col">
      <div className="flex h-44 items-end justify-center">
        <Robot kind={robot} mood={mood(result, running)} title={`${label} robot`} className="h-40" />
      </div>
      <div className={`mt-2 flex flex-1 flex-col rounded-md border bg-surface p-4 ${kind === 'own' ? 'border-brand/60' : 'border-line'}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate font-semibold">{label}</div>
            <div className="text-xs text-muted">{kind === 'own' ? 'Your model' : 'Outside model'}</div>
          </div>
          {result?.status === 'ok' && result.level && <LevelBadge level={result.level} />}
        </div>

        {running && <p className="mt-4 text-sm text-muted">Working...</p>}
        {result && <ResultBody r={result} />}
      </div>
    </div>
  )
}

function ResultBody({ r }: { r: ArenaRunResult }) {
  if (r.status === 'off') {
    return <p className="mt-4 text-sm text-muted">Not run. {r.error ?? 'This model is turned off on this server.'}</p>
  }
  if (r.status === 'error') {
    return (
      <p className="mt-4 text-sm">
        <span className="font-semibold text-lv-red">Failed.</span> <span className="text-ink">{r.error ?? 'This model did not answer.'}</span>
      </p>
    )
  }
  return (
    <div className="mt-4 flex min-w-0 flex-col gap-3">
      <div>
        <div className="text-xs text-muted">Answer</div>
        <div className="mt-0.5 font-mono text-lg text-ink">{r.answer_text ?? <span className="font-sans text-sm text-muted">No answer shown</span>}</div>
      </div>
      {r.reasons.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {r.reasons.map((x) => (
            <ReasonChip key={x.code + x.text}>{x.text}</ReasonChip>
          ))}
        </div>
      )}
      <div className="text-xs text-muted">
        {r.n_attempts > 0 && !r.reasons.some((x) => x.code === 'agreement') && `${r.agree} of ${r.n_attempts} attempts agree. `}
        {r.cache_hit ? 'From the cache.' : `Took ${seconds(r.latency_ms)}.`}
      </div>
      {r.sql && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-brand-text">SQL</summary>
          <div className="mt-2">
            <SqlBlock sql={r.sql} />
          </div>
        </details>
      )}
      {r.columns.length > 0 && r.rows.length > 1 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-brand-text">Rows ({r.rows.length})</summary>
          <div className="mt-2 overflow-x-auto">
            <ResultTable columns={r.columns} rows={r.rows} max={20} />
          </div>
        </details>
      )}
    </div>
  )
}

function CachedRun({ data }: { data: unknown }) {
  const run = asRun(data)
  if (!run) {
    return <p className="mt-4 text-sm text-muted">This saved run is in a format this page does not know yet, so it is not shown.</p>
  }
  const n = run.results.length
  return (
    <div className="mt-4">
      {run.question && <p className="mb-2 text-sm text-ink">{run.question}</p>}
      <div className={`grid grid-cols-1 gap-6 ${n >= 3 ? 'lg:grid-cols-3' : n === 2 ? 'md:grid-cols-2' : ''} ${n === 4 ? 'xl:grid-cols-4' : ''}`}>
        {run.results.map((r) => (
          <ModelColumn key={r.model_id} label={r.label} kind={r.kind} robot={robotKind(r)} result={r} running={false} />
        ))}
      </div>
    </div>
  )
}
