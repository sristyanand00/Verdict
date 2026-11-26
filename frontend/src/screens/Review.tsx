// Review queue: every answer Verdict was not sure about (Review or Reject), plus Trusted answers
// the analyst flagged as wrong. The analyst opens one to approve, fix or reject it.

import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { LevelBadge, ReasonChip } from '../components/LevelBadge'
import { api } from '../lib/api'
import { timeAgo } from '../lib/format'
import type { Level, ReviewList, ReviewStatus } from '../lib/types'

const STATUS_LABEL: Record<ReviewStatus, string> = { open: 'Open', approved: 'Approved', fixed: 'Fixed', rejected: 'Rejected' }

export default function Review() {
  const [data, setData] = useState<ReviewList | null>(null)
  const [show, setShow] = useState<'open' | ''>('open')
  const [level, setLevel] = useState<Level | 'all'>('all')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.reviewList(show).then(setData).catch((e) => setError(e instanceof Error ? e.message : 'Could not load the queue'))
  }, [show])

  const items = (data?.items ?? []).filter((i) => level === 'all' || i.level === level)

  return (
    <div className="mx-auto max-w-[72rem]">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mb-1 text-3xl font-bold">Review queue</h1>
          <p className="text-muted">Answers Verdict was not sure about, and Trusted answers you flagged. Approve, fix or reject each one.</p>
        </div>
        {data && (
          <div className="flex gap-2 text-sm">
            <span className="rounded-lg border border-lv-red/40 bg-lv-red-tint px-3 py-1.5 font-semibold text-lv-red">Reject {data.open_counts.reject}</span>
            <span className="rounded-lg border border-lv-yellow/40 bg-lv-yellow-tint px-3 py-1.5 font-semibold text-lv-yellow">Review {data.open_counts.review}</span>
          </div>
        )}
      </div>

      {/* filters */}
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <Seg active={show === 'open'} onClick={() => setShow('open')}>Open</Seg>
        <Seg active={show === ''} onClick={() => setShow('')}>All, including resolved</Seg>
        <span className="mx-2 h-5 w-px bg-line" />
        <Seg active={level === 'all'} onClick={() => setLevel('all')}>All levels</Seg>
        <Seg active={level === 'review'} onClick={() => setLevel('review')}>Review</Seg>
        <Seg active={level === 'reject'} onClick={() => setLevel('reject')}>Reject</Seg>
        <Seg active={level === 'trusted'} onClick={() => setLevel('trusted')}>Flagged Trusted</Seg>
      </div>

      {error && <p className="rounded-xl border border-lv-red/50 bg-lv-red-tint p-4 text-sm">{error}</p>}

      {data && items.length === 0 && (
        <div className="rounded-2xl border border-dashed border-line p-10 text-center text-muted">
          {show === 'open' ? 'Nothing to review. Every open question has been handled.' : 'Nothing here yet.'}
        </div>
      )}

      <ul className="overflow-hidden rounded-2xl border border-line">
        {items.map((it) => (
          <li key={it.review_id} className="border-b border-line last:border-b-0">
            <Link to={`/review/${it.review_id}`} className="flex items-start gap-4 bg-surface px-5 py-4 hover:bg-surface-2">
              <div className="w-24 shrink-0 pt-0.5"><LevelBadge level={it.level} /></div>
              <div className="min-w-0 flex-1">
                <div className="mb-1.5 font-semibold">{it.question}</div>
                <div className="flex flex-wrap gap-1.5">
                  {it.source === 'flagged' && <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-bold text-on-accent">Flagged by you</span>}
                  {it.reasons.map((r) => <ReasonChip key={r.code + r.text}>{r.text}</ReasonChip>)}
                </div>
              </div>
              <div className="shrink-0 text-right text-xs text-muted">
                <div>{timeAgo(it.created_at)}</div>
                {it.status !== 'open' && <div className="mt-1 font-semibold text-lv-green">{STATUS_LABEL[it.status]}</div>}
              </div>
            </Link>
          </li>
        ))}
      </ul>

      {data && (
        <p className="mt-5 text-sm text-muted">
          Today: {data.today.asked} asked, {data.today.trusted} Trusted with no human needed, {data.today.review} Review, {data.today.reject} Reject.
        </p>
      )}
    </div>
  )
}

function Seg({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} className={`rounded-full px-3.5 py-1.5 ${active ? 'bg-brand text-on-brand' : 'border border-line text-muted hover:text-ink'}`}>
      {children}
    </button>
  )
}
