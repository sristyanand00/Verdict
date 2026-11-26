// Trust Report: what the evaluation measured, from GET /api/results (results/results.json).
// 404 means the evaluation has not written the file yet. Only fields whose shape is fixed in
// docs/API.md are shown (tested_trust and arena_models); nothing is filled in or guessed.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../lib/api'
import { formatDate, percent, range } from '../lib/format'
import type { ArenaScore, TestedTrust } from '../lib/types'

function isTestedTrust(x: unknown): x is TestedTrust {
  const t = x as TestedTrust
  return !!t && typeof t === 'object' && typeof t.precision === 'number' && typeof t.low === 'number' && typeof t.high === 'number'
}

export default function TrustReport() {
  const [results, setResults] = useState<Record<string, unknown> | null>(null)
  const [missing, setMissing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .results()
      .then(setResults)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) setMissing(true)
        else setError(e instanceof Error ? e.message : 'Could not load the results')
      })
  }, [])

  const tested = results && isTestedTrust(results.tested_trust) ? results.tested_trust : null
  const scores = results && Array.isArray(results.arena_models) ? (results.arena_models as ArenaScore[]) : []

  return (
    <div className="max-w-[56rem]">
      <h1 className="text-2xl font-semibold">Trust Report</h1>
      <p className="mt-1 text-sm text-muted">How often each level was right on questions with a known answer. Only measured numbers are shown, each with its range.</p>

      {error && <p className="mt-8 text-sm text-lv-red">{error}</p>}
      {!results && !missing && !error && <p className="mt-8 text-sm text-muted">Loading...</p>}

      {missing && (
        <div className="mt-8 border-y border-line py-6">
          <div className="font-medium text-ink">Results not ready yet</div>
          <p className="mt-1 text-sm text-muted">
            The evaluation has not been run on this server, so there are no measured numbers to show. Until then, Verdict does not claim how often a
            Trusted answer is right.
          </p>
        </div>
      )}

      {results && (
        <>
          <section className="mt-8">
            <h2 className="text-sm font-semibold">Trusted answers in testing</h2>
            {tested ? (
              <p className="mt-2 text-sm text-ink">
                Right <span className="font-mono">{percent(tested.precision)}</span> of the time{' '}
                <span className="text-muted">
                  (range {range(tested.low, tested.high)}), on {tested.on}.
                </span>
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted">Not measured yet.</p>
            )}
          </section>

          <section className="mt-10">
            <h2 className="text-sm font-semibold">Models on a full benchmark</h2>
            {scores.length === 0 ? (
              <p className="mt-2 text-sm text-muted">Not measured yet.</p>
            ) : (
              <table className="mt-3 w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs text-muted">
                    <th className="py-2 pr-4 font-medium">Model</th>
                    <th className="py-2 pr-4 font-medium">Benchmark</th>
                    <th className="py-2 pr-4 text-right font-medium">Accuracy</th>
                    <th className="py-2 font-medium">Measured</th>
                  </tr>
                </thead>
                <tbody>
                  {scores.map((s) => (
                    <tr key={`${s.model_id}-${s.benchmark}`} className="border-b border-line/60">
                      <td className="py-2.5 pr-4 text-ink">{s.label}</td>
                      <td className="py-2.5 pr-4 text-muted">
                        {s.benchmark}
                        {s.n_questions ? `, ${s.n_questions.toLocaleString('en-US')} questions` : ''}
                      </td>
                      <td className="py-2.5 pr-4 text-right font-mono tabular-nums">
                        {typeof s.accuracy === 'number' ? `${(s.accuracy * 100).toFixed(1)}%` : <span className="font-sans text-muted">Not measured yet</span>}
                      </td>
                      <td className="py-2.5 text-muted">{s.measured_at ? formatDate(s.measured_at) : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="mt-3 text-xs text-muted">
              Try the models on your own question in the <Link to="/arena" className="text-brand-text hover:underline">Model Arena</Link>.
            </p>
          </section>
        </>
      )}
    </div>
  )
}
