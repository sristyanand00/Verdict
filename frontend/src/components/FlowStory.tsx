// Animated story of how a verdict is made. It loops on its own:
// the analyst needs an answer, Verdict steps in, writes 8 attempts, runs them safely,
// groups the results, runs the checks, and hands back a Trusted answer.
// The numbers are an example, not a real result.

import { useEffect, useState } from 'react'
import { LevelBadge } from './LevelBadge'

const QUESTION = 'How many orders were delivered late in 2018?'

const STEPS = [
  { title: 'Question', body: 'The analyst asks in plain English.' },
  { title: '8 SQL attempts', body: 'Verdict writes the query eight separate times.' },
  { title: 'Safe run', body: 'Each runs read-only, in its own process, with a time limit.' },
  { title: 'Group', body: 'Attempts with the same result are grouped together.' },
  { title: 'Checks', body: 'Agreement, empty results, two meanings, conflicts.' },
  { title: 'Verdict', body: 'Trusted, Review or Reject, with the reasons.' },
]

const PHASES: { step: number; ms: number; caption: string; status: string }[] = [
  { step: 0, ms: 3000, caption: 'The analyst needs a number for a meeting. Can the AI answer be trusted?', status: '' },
  { step: 0, ms: 1800, caption: 'Verdict steps in.', status: 'On it.' },
  { step: 1, ms: 2600, caption: 'Verdict writes the SQL eight separate times.', status: 'Writing 8 attempts...' },
  { step: 2, ms: 2600, caption: 'Each attempt runs read-only, in its own process, with a time limit.', status: 'Running safely...' },
  { step: 3, ms: 2600, caption: 'Attempts that give the same answer are grouped together.', status: 'Grouping results...' },
  { step: 4, ms: 3200, caption: 'Then the checks run. Only checks that really run are shown.', status: 'Checking...' },
  { step: 5, ms: 4200, caption: 'A Trusted answer goes back to the analyst, with the evidence one click away.', status: 'Done.' },
]

const SQL_LINES = [
  [70, 45, 85], [60, 50, 80], [75, 40, 70], [65, 55, 90],
  [70, 45, 75], [55, 60, 85], [80, 40, 65], [60, 50, 88],
]
const ODD_ONE = 5 // the one attempt that gives a different number

const CHECKS = [
  'Safe: read-only, nothing blocked',
  'Ran: 8 of 8 ran',
  'Agreement: 7 of 8 give the same answer',
  'Not empty',
  'No split into two meanings',
  'No conflict with approved answers',
]

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function FlowStory() {
  const [phase, setPhase] = useState(() => (prefersReducedMotion() ? PHASES.length - 1 : 0))
  const [playing, setPlaying] = useState(() => !prefersReducedMotion())
  const [typed, setTyped] = useState(0)

  // advance through the phases
  useEffect(() => {
    if (!playing) return
    const t = setTimeout(() => setPhase((p) => (p + 1) % PHASES.length), PHASES[phase].ms)
    return () => clearTimeout(t)
  }, [phase, playing])

  // type the question out during the first phase
  useEffect(() => {
    if (phase !== 0) {
      setTyped(QUESTION.length)
      return
    }
    setTyped(0)
    const t = setInterval(() => setTyped((n) => (n >= QUESTION.length ? n : n + 1)), 38)
    return () => clearInterval(t)
  }, [phase])

  const cur = PHASES[phase]
  const done = phase === PHASES.length - 1

  return (
    <div>
      {/* step tracker */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {STEPS.map((s, i) => {
          const active = cur.step === i
          const past = cur.step > i
          return (
            <button
              key={s.title}
              onClick={() => {
                setPhase(PHASES.findIndex((p) => p.step === i))
                setPlaying(false)
              }}
              className={`relative min-w-0 overflow-hidden rounded-2xl border p-4 text-left transition-all duration-500 ${
                active
                  ? 'border-brand bg-brand/15 shadow-[0_0_40px_-8px_rgba(21,88,201,.8)]'
                  : past
                    ? 'border-accent/40 bg-surface'
                    : 'border-line bg-surface opacity-60'
              }`}
            >
              <div className="mb-2.5 flex items-center justify-between">
                <span
                  className={`grid h-7 w-7 place-items-center rounded-lg text-xs font-black transition-colors duration-500 ${
                    past ? 'bg-accent text-on-accent' : 'bg-brand text-on-brand'
                  }`}
                >
                  {past ? (
                    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5"><path d="M3 8.5l3.2 3.2L13 4.8" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" /></svg>
                  ) : (
                    i + 1
                  )}
                </span>
              </div>
              <div className="mb-1 font-bold">{s.title}</div>
              <div className="text-xs leading-snug text-muted">{s.body}</div>
              {active && playing && (
                <span key={phase} className="anim-fill absolute bottom-0 left-0 h-[3px] bg-accent" style={{ animationDuration: `${cur.ms}ms` }} />
              )}
            </button>
          )
        })}
      </div>

      {/* stage */}
      <div className="relative mt-4 overflow-hidden rounded-3xl border border-brand/40 bg-[linear-gradient(180deg,rgba(21,88,201,.12),rgba(18,19,22,.9))] p-6">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(91,141,239,.07)_1px,transparent_1px),linear-gradient(90deg,rgba(91,141,239,.07)_1px,transparent_1px)] bg-[size:2rem_2rem]" />

        <div className="relative grid min-h-[22rem] grid-cols-[9rem_1fr_9rem] items-center gap-6">
          {/* analyst */}
          <div className="flex flex-col items-center gap-2 self-end">
            <div key={`a-${done}`} className={`anim-pop max-w-[9rem] rounded-2xl rounded-bl-sm border px-3 py-2 text-xs ${done ? 'border-lv-green/50 bg-lv-green-tint text-ink' : 'border-line bg-surface text-ink'}`}>
              {done ? '6,535, Trusted. I can use this.' : phase === 0 ? 'I need this for the 3 pm meeting.' : 'Can I trust the answer?'}
            </div>
            <AnalystBust happy={done} />
            <span className="text-[0.65rem] font-bold tracking-[0.16em] text-muted">ANALYST</span>
          </div>

          {/* work area */}
          <div className="flex min-w-0 flex-col items-center justify-center">
            <Work phase={phase} typed={typed} />
          </div>

          {/* Verdict */}
          <div
            className={`flex flex-col items-center gap-2 self-end transition-all duration-700 ${
              phase === 0 ? 'translate-x-24 opacity-0' : 'translate-x-0 opacity-100'
            }`}
          >
            <div key={`s-${phase}`} className="anim-pop max-w-[9rem] rounded-2xl rounded-br-sm border border-brand/60 bg-brand/20 px-3 py-2 text-xs text-ink">
              {cur.status || '...'}
            </div>
            <VerdictBust happy={done} />
            <span className="text-[0.65rem] font-bold tracking-[0.16em] text-muted">VERDICT</span>
          </div>
        </div>

        {/* caption and controls */}
        <div className="relative mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
          <p key={`c-${phase}`} className="anim-pop text-sm text-ink">{cur.caption}</p>
          <div className="flex items-center gap-2">
            <span className="text-[0.7rem] text-muted">Example, not a real result</span>
            <button onClick={() => setPlaying((p) => !p)} className="rounded-full border border-line px-3 py-1 text-xs text-ink hover:border-brand">
              {playing ? 'Pause' : 'Play'}
            </button>
            <button
              onClick={() => {
                setPhase(0)
                setPlaying(true)
              }}
              className="rounded-full border border-line px-3 py-1 text-xs text-ink hover:border-brand"
            >
              Replay
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function Work({ phase, typed }: { phase: number; typed: number }) {
  if (phase <= 1) {
    return (
      <div className="w-full max-w-[34rem] rounded-2xl border border-line bg-surface p-5">
        <div className="mb-2 text-[0.7rem] font-extrabold uppercase tracking-[0.14em] text-muted">Question</div>
        <div className="font-mono text-lg">
          {QUESTION.slice(0, typed)}
          {typed < QUESTION.length && <span className="ml-0.5 inline-block h-5 w-2 translate-y-1 animate-pulse bg-accent" />}
        </div>
      </div>
    )
  }

  if (phase <= 3) {
    const ran = phase === 3
    return (
      <div className="grid w-full max-w-[44rem] grid-cols-4 gap-3">
        {SQL_LINES.map((lines, i) => (
          <div
            key={i}
            className="anim-pop relative overflow-hidden rounded-xl border border-line bg-bg/80 p-3"
            style={{ animationDelay: phase === 2 ? `${i * 110}ms` : '0ms' }}
          >
            <div className="mb-2 flex items-center justify-between text-[0.6rem] text-muted">
              <span>Attempt {i + 1}</span>
              {ran && <span className="anim-pop rounded bg-lv-green-tint px-1.5 font-bold text-lv-green" style={{ animationDelay: `${i * 120}ms` }}>RAN</span>}
            </div>
            {lines.map((w, j) => (
              <div key={j} className="mb-1.5 h-1.5 rounded-full" style={{ width: `${w}%`, background: j === 0 ? 'var(--color-brand-text)' : 'var(--color-line)' }} />
            ))}
            {ran && (
              <div className="anim-pop mt-2 font-mono text-sm font-bold" style={{ animationDelay: `${i * 120 + 200}ms` }}>
                {i === ODD_ONE ? '6,702' : '6,535'}
              </div>
            )}
            {ran && <span className="anim-scan pointer-events-none absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-brand/30 to-transparent" style={{ animationDelay: `${i * 120}ms` }} />}
          </div>
        ))}
        {ran && (
          <div className="anim-pop col-span-4 flex items-center justify-center gap-2 text-xs text-muted">
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="var(--color-accent)" strokeWidth={2}><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
            Read-only connection. Each attempt in its own process. Time limit on every run.
          </div>
        )}
      </div>
    )
  }

  if (phase === 4) {
    return (
      <div className="grid w-full max-w-[40rem] grid-cols-[2fr_1fr] gap-4">
        <div className="anim-pop rounded-2xl border border-lv-green/50 bg-lv-green-tint/60 p-5">
          <div className="mb-3 text-xs font-bold text-muted">Group A: 7 attempts</div>
          <div className="mb-3 flex gap-2">
            {Array.from({ length: 7 }, (_, i) => (
              <span key={i} className="anim-pop h-5 w-5 rounded-full bg-lv-green" style={{ animationDelay: `${i * 90}ms` }} />
            ))}
          </div>
          <div className="font-mono text-3xl font-bold">6,535</div>
        </div>
        <div className="anim-pop rounded-2xl border border-line bg-surface p-5" style={{ animationDelay: '400ms' }}>
          <div className="mb-3 text-xs font-bold text-muted">Group B: 1 attempt</div>
          <div className="mb-3 flex gap-2">
            <span className="h-5 w-5 rounded-full border-2 border-lv-yellow" />
          </div>
          <div className="font-mono text-3xl font-bold text-muted">6,702</div>
        </div>
      </div>
    )
  }

  if (phase === 5) {
    return (
      <ul className="w-full max-w-[34rem] space-y-2">
        {CHECKS.map((c, i) => (
          <li key={c} className="anim-pop flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-2.5 text-sm" style={{ animationDelay: `${i * 380}ms` }}>
            <span className="rounded bg-lv-green-tint px-2 py-0.5 text-[0.65rem] font-black tracking-wider text-lv-green">PASS</span>
            {c}
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className="flex flex-col items-center gap-5">
      <div className="anim-stamp">
        <LevelBadge level="trusted" big />
      </div>
      <div className="anim-pop rounded-2xl border border-line bg-surface px-8 py-5 text-center" style={{ animationDelay: '350ms' }}>
        <div className="mb-1 text-xs text-muted">{QUESTION}</div>
        <div className="font-mono text-4xl font-bold">6,535</div>
        <div className="mt-2 text-xs text-muted">7 of 8 agree, all checks passed. Evidence one click away.</div>
      </div>
    </div>
  )
}

function AnalystBust({ happy }: { happy: boolean }) {
  return (
    <svg viewBox="0 0 120 120" className="h-28 w-28">
      <path d="M14 120 Q14 82 60 80 Q106 82 106 120 Z" fill="#232a3a" stroke="#3a4458" strokeWidth={1.5} />
      <path d="M50 81 L60 100 L70 81 Z" fill="#e8ecf2" />
      <path d="M53 82 L60 112 L67 82" fill="none" stroke="var(--color-accent)" strokeWidth={1.6} />
      <rect x={52} y={62} width={16} height={22} rx={5} fill="#d9a27e" />
      <circle cx={34} cy={46} r={5} fill="#d9a27e" />
      <circle cx={60} cy={44} r={27} fill="#d9a27e" stroke="#a8714f" strokeWidth={1} />
      <path d="M32 42 Q31 13 61 14 Q91 15 87 46 Q81 29 61 29 Q41 30 32 42 Z" fill="#1e1a1a" />
      <circle cx={51} cy={45} r={7} fill="none" stroke="#1e1a1a" strokeWidth={1.8} />
      <circle cx={71} cy={45} r={7} fill="none" stroke="#1e1a1a" strokeWidth={1.8} />
      <line x1={58} y1={45} x2={64} y2={45} stroke="#1e1a1a" strokeWidth={1.8} />
      <circle cx={51} cy={46} r={2} fill="#1e1a1a" />
      <circle cx={71} cy={46} r={2} fill="#1e1a1a" />
      <path d={happy ? 'M50 58 Q60 66 70 58' : 'M52 60 Q60 57 68 60'} fill="none" stroke="#1e1a1a" strokeWidth={2} strokeLinecap="round" />
    </svg>
  )
}

function VerdictBust({ happy }: { happy: boolean }) {
  return (
    <svg viewBox="0 0 120 120" className="h-28 w-28 overflow-visible">
      <rect className="r-body" x={22} y={86} width={76} height={40} rx={20} />
      <rect className="r-panel" x={48} y={94} width={24} height={18} rx={6} />
      <path className="r-check" style={{ strokeWidth: 3 }} d="M53 103 L58 108 L67 98" />
      <rect className="r-joint" x={52} y={74} width={16} height={14} rx={4} />
      <line x1={42} y1={14} x2={38} y2={2} stroke="var(--color-robot-line)" strokeWidth={2.5} strokeLinecap="round" />
      <line x1={78} y1={14} x2={82} y2={2} stroke="var(--color-robot-line)" strokeWidth={2.5} strokeLinecap="round" />
      <circle className="r-ball on" cx={38} cy={2} r={4} />
      <circle className="r-ball on" cx={82} cy={2} r={4} />
      <circle className="r-joint" cx={18} cy={44} r={9} />
      <circle className="r-joint" cx={102} cy={44} r={9} />
      <rect className="r-body" x={18} y={10} width={84} height={68} rx={32} />
      <rect className="r-visor" x={28} y={26} width={64} height={38} rx={19} />
      {happy ? (
        <>
          <path className="r-line" strokeWidth={3.5} d="M38 48 Q45 39 52 48" />
          <path className="r-line" strokeWidth={3.5} d="M68 48 Q75 39 82 48" />
        </>
      ) : (
        <g className="anim-blink">
          <circle className="r-eye" cx={46} cy={45} r={7} />
          <circle className="r-eye" cx={74} cy={45} r={7} />
        </g>
      )}
    </svg>
  )
}
