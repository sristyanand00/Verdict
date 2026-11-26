// Entrance animations for the hero. They play once on load and then stay still.
// Words are kept on one line each (whitespace-nowrap) so letters never wrap mid-word.

import { Fragment, type ReactNode } from 'react'

type Segment = { text: string; highlight?: boolean; bold?: boolean }

// Headline: every letter rises into place, one after another.
export function AnimatedHeadline({ segments, startMs = 0, stepMs = 28 }: { segments: Segment[]; startMs?: number; stepMs?: number }) {
  let n = 0
  const out: ReactNode[] = []

  segments.forEach((seg, si) => {
    const words = seg.text.split(' ')
    const segStart = startMs + n * stepMs
    const wordNodes = words.map((word, wi) => {
      const letters = [...word].map((ch, li) => {
        const delay = startMs + n++ * stepMs
        return (
          <span key={li} className="anim-letter" style={{ animationDelay: `${delay}ms` }}>
            {ch}
          </span>
        )
      })
      return (
        <Fragment key={wi}>
          <span className="inline-block whitespace-nowrap">{letters}</span>
          {wi < words.length - 1 ? ' ' : null}
        </Fragment>
      )
    })

    if (seg.highlight) {
      out.push(
        <span key={si} className="relative inline-block -rotate-1 px-[.14em] text-on-accent">
          <span
            aria-hidden
            className="anim-sweep absolute inset-0 rounded-[.12em] bg-accent"
            style={{ animationDelay: `${Math.max(0, segStart - 120)}ms` }}
          />
          <span className="relative">{wordNodes}</span>
        </span>,
      )
    } else {
      out.push(<span key={si}>{wordNodes}</span>)
    }
  })

  // spaces between segments
  const joined: ReactNode[] = []
  out.forEach((node, i) => {
    joined.push(node)
    if (i < out.length - 1) joined.push(' ')
  })

  return <>{joined}</>
}

// Paragraph: words fade up one after another.
export function AnimatedWords({ segments, startMs = 0, stepMs = 22 }: { segments: Segment[]; startMs?: number; stepMs?: number }) {
  let n = 0
  return (
    <>
      {segments.map((seg, si) => {
        const words = seg.text.split(' ').filter(Boolean)
        const nodes = words.map((w, wi) => (
          <span key={wi} className="anim-word inline-block" style={{ animationDelay: `${startMs + n++ * stepMs}ms` }}>
            {w}
            {' '}
          </span>
        ))
        return seg.bold ? (
          <b key={si} className="font-semibold text-ink">{nodes}</b>
        ) : (
          <span key={si}>{nodes}</span>
        )
      })}
    </>
  )
}
