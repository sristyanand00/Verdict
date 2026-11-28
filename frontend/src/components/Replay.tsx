// Replay: shows a stored answer being built step by step, for recordings.
// Every query, status and result shown here comes from the stored answer;
// only the timing is replayed. Turned on with /ask?replay=1, off with /ask?replay=0.

import { useEffect, useState } from 'react'
import type { AskResponse, Attempt } from '../lib/types'

const KEY = 'verdict.replay'

export function replayOn(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function setReplay(on: boolean) {
  try {
    if (on) localStorage.setItem(KEY, '1')
    else localStorage.removeItem(KEY)
  } catch {
    // storage not available: replay stays off
  }
}

const WRITE_MS = 550
const RUN_MS = 320
const STEP_MS = 1000

function cell(v: unknown): string {
  if (v === null || v === undefined) return 'NULL'
  if (typeof v === 'number') return v.toLocaleString('en-US')
  return String(v)
}

function resultOf(ask: AskResponse, a: Attempt): string {
  if (a.kind === 'cannot_answer') return 'said: cannot answer'
  if (a.kind === 'empty') return 'no SQL'
  if (a.status !== 'ok') return a.status ?? 'failed'
  const g = a.group === null ? undefined : ask.groups[a.group]
  if (!g) return 'ran'
  if (g.preview.length === 1 && g.preview[0].length === 1) return cell(g.preview[0][0])
  return `${g.row_count} ${g.row_count === 1 ? 'row' : 'rows'}`
}

function groupLabel(ask: AskResponse, i: number): string {
  const g = ask.groups[i]
  const value = g.preview.length === 1 && g.preview[0].length === 1 ? cell(g.preview[0][0]) : `${g.row_count} rows`
  return `${value}  x ${g.size}`
}

export function Replay({ ask, onDone }: { ask: AskResponse; onDone: () => void }) {
  const n = ask.attempts.length
  // tick counts up; each range of ticks is one stage
  const [written, setWritten] = useState(0)
  const [ran, setRan] = useState(0)
  const [stage, setStage] = useState<1 | 2 | 3 | 4>(1)

  useEffect(() => {
    const timers: number[] = []
    let t = 300
    for (let i = 1; i <= n; i++) {
      timers.push(window.setTimeout(() => setWritten(i), t))
      t += WRITE_MS
    }
    timers.push(window.setTimeout(() => setStage(2), t))
    t += 300
    for (let i = 1; i <= n; i++) {
      timers.push(window.setTimeout(() => setRan(i), t))
      t += RUN_MS
    }
    timers.push(window.setTimeout(() => setStage(3), t))
    t += STEP_MS
    timers.push(window.setTimeout(() => setStage(4), t))
    t += STEP_MS
    timers.push(window.setTimeout(onDone, t))
    return () => timers.forEach((id) => window.clearTimeout(id))
    // onDone is stable for the life of one replay
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ask.ask_id])

  const steps: [number, string][] = [
    [1, `Writing ${n} SQL attempts`],
    [2, 'Running each query in the read-only sandbox'],
    [3, 'Grouping the attempts that gave the same result'],
    [4, 'Running the checks'],
  ]

  return (
    <div className="rounded-2xl border border-brand/40 bg-surface p-6">
      <div className="mb-4 text-sm text-muted">"{ask.question}"</div>

      <ol className="mb-5 space-y-1.5">
        {steps.map(([k, label]) => (
          <li key={k} className={`flex items-center gap-3 text-sm ${stage === k ? 'font-semibold text-ink' : stage > k ? 'text-muted' : 'text-muted/40'}`}>
            {stage === k ? (
              <svg viewBox="0 0 24 24" className="anim-spin h-4 w-4 shrink-0" fill="none" stroke="var(--color-accent)" strokeWidth={2.5}>
                <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
              </svg>
            ) : (
              <span className={`inline-block h-4 w-4 shrink-0 text-center leading-4 ${stage > k ? 'text-lv-green' : ''}`}>{stage > k ? '✓' : '·'}</span>
            )}
            {label}
            {k === 1 && stage === 1 && <span className="font-normal text-muted">{written} of {n}</span>}
            {k === 2 && stage === 2 && <span className="font-normal text-muted">{ran} of {n}</span>}
          </li>
        ))}
      </ol>

      <ul className="space-y-1.5">
        {ask.attempts.slice(0, written).map((a, i) => {
          const done = i < ran
          const ok = a.kind === 'sql' && a.status === 'ok'
          return (
            <li key={a.index} className="anim-rise flex items-center gap-3 rounded-lg border border-line bg-surface-2 px-3 py-2">
              <span className="w-5 shrink-0 text-xs text-muted">{i + 1}</span>
              <code className="min-w-0 flex-1 truncate font-mono text-xs text-ink">{a.sql ?? (a.kind === 'cannot_answer' ? 'CANNOT_ANSWER' : '(no SQL)')}</code>
              <span className={`w-36 shrink-0 text-right font-mono text-xs ${!done ? 'text-muted/40' : ok ? 'text-lv-green' : 'text-lv-red'}`}>
                {done ? resultOf(ask, a) : stage >= 2 ? 'running' : 'waiting'}
              </span>
            </li>
          )
        })}
      </ul>

      {stage >= 3 && ask.groups.length > 0 && (
        <div className="anim-rise mt-4 flex flex-wrap items-center gap-2 text-xs text-muted">
          Groups:
          {ask.groups.map((_, i) => (
            <span key={i} className={`rounded-md border px-2.5 py-1 font-mono ${i === 0 ? 'border-brand text-ink' : 'border-line'}`}>{groupLabel(ask, i)}</span>
          ))}
        </div>
      )}
    </div>
  )
}
