// Intro screen: headline, how a verdict is made, and tested numbers.
// Tested numbers stay empty until the full evaluation writes results.json.

import { Link } from 'react-router-dom'
import { LevelBadge } from '../components/LevelBadge'
import { AnimatedHeadline, AnimatedWords } from '../components/AnimatedText'
import { FlowStory } from '../components/FlowStory'
import { Handshake } from '../components/Handshake'
import { Logo } from '../components/Logo'

const BTN = 'inline-flex items-center gap-2.5 rounded-full border-[0.0938rem] px-[1.375rem] py-3 text-sm font-bold transition-transform hover:-translate-y-px'

const FACTS: { title: string; body: string }[] = [
  { title: 'Read-only, always', body: 'Your database is never changed' },
  { title: 'Our own model', body: 'A Qwen model the team trained, not a cloud API' },
  { title: 'Reasons, not scores', body: 'Every verdict says why' },
]

const SOURCES = ['Olist e-commerce', 'BIRD benchmark databases', 'Your CSV or Excel', 'Any SQLite file']

export default function Landing() {
  return (
    <div className="relative overflow-hidden">
      <Backdrop />
      <div className="relative mx-auto w-full max-w-[110rem] px-8 pb-12 xl:px-14 2xl:px-20">
      <header className="flex items-center gap-7 py-[1.375rem]">
        <Logo />
        <nav className="flex gap-[1.375rem] text-[0.8125rem] tracking-wide text-muted">
          <a href="#how">How it works</a>
          <Link to="/trust">Trust Report</Link>
          <Link to="/arena">Model Arena</Link>
        </nav>
        <div className="flex-1" />
        <Link to="/ask" className={`${BTN} border-transparent bg-accent px-4 py-2 text-xs text-on-accent`}>
          Open Verdict <span aria-hidden>&rarr;</span>
        </Link>
      </header>

      {/* hero: one centred column */}
      <section className="relative flex min-h-[calc(100vh-200px)] flex-col items-center justify-center py-10 text-center">
        <div className="anim-rise mb-7 inline-flex items-center gap-2 rounded-full border border-brand/60 bg-brand/15 px-3 py-1 text-xs text-ink">
          <span className="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_10px_2px_rgba(212,255,36,.7)]" />
          Private mode: runs on a model we trained ourselves
        </div>
        <div className="anim-rise mb-[1.375rem] flex items-center gap-3 text-xs uppercase tracking-[0.16em] text-muted" style={{ animationDelay: '150ms' }}>
          <span className="h-0.5 w-[1.625rem] bg-accent" />
          Can I trust this?
          <span className="h-0.5 w-[1.625rem] bg-accent" />
        </div>
        <h1 aria-label="The trust layer for AI-generated analytics." className="mb-7 max-w-[62rem] text-[3.75rem] font-black leading-[1.03] tracking-[-0.025em] lg:text-[4.75rem]">
          <span aria-hidden>
            <AnimatedHeadline startMs={300} stepMs={30} segments={[{ text: 'The trust layer for' }, { text: 'AI-generated', highlight: true }, { text: 'analytics.' }]} />
          </span>
        </h1>
        <p className="mb-9 max-w-[42rem] text-lg leading-relaxed text-muted lg:text-xl">
          <AnimatedWords
            startMs={1250}
            segments={[
              { text: 'Verdict writes the SQL eight times, runs every attempt safely, and gives each answer a verdict:' },
              { text: 'Trusted, Review or Reject,', bold: true },
              { text: 'with the reasons and the evidence behind it.' },
            ]}
          />
        </p>
        <div className="anim-rise flex flex-wrap justify-center gap-3" style={{ animationDelay: '1900ms' }}>
          <Link to="/ask" className={`${BTN} border-transparent bg-brand text-on-brand`}>
            Check a question <span aria-hidden>&rarr;</span>
          </Link>
          <a href="#how" className={`${BTN} border-line bg-bg/40 text-ink backdrop-blur`}>How a verdict is made</a>
        </div>

        <div className="mt-14 grid w-full max-w-[52rem] grid-cols-3 gap-4 text-left">
          {FACTS.map((f, i) => (
            <div key={f.title} style={{ animationDelay: `${2150 + i * 130}ms` }} className="anim-rise rounded-xl border border-brand/30 bg-surface/60 px-4 py-3 backdrop-blur">
              <div className="text-sm font-bold">{f.title}</div>
              <div className="text-xs text-muted">{f.body}</div>
            </div>
          ))}
        </div>
      </section>

      {/* where it runs */}
      <section className="flex flex-wrap items-center gap-x-8 gap-y-3 border-y border-brand/30 bg-brand/[0.06] px-6 py-5">
        <span className="text-xs font-extrabold uppercase tracking-[0.16em] text-brand-text">Works with</span>
        {SOURCES.map((s) => (
          <span key={s} className="flex items-center gap-2 text-sm text-muted">
            <span className="h-1.5 w-1.5 rotate-45 bg-brand-text" />
            {s}
          </span>
        ))}
      </section>

      {/* Verdict and the analyst need each other */}
      <section id="together" className="pt-24">
        <div className="mb-10 text-center">
          <h2 className="mb-2 text-[2.125rem] font-bold tracking-tight">Verdict and the analyst need each other</h2>
          <p className="mx-auto max-w-[44rem] text-muted">
            Verdict takes the routine checking off the analyst. The analyst gives Verdict the judgement it cannot have on its own.
          </p>
        </div>
        <div className="grid grid-cols-1 items-center gap-8 lg:grid-cols-[1fr_1.5fr_1fr]">
          <GiveList
            title="What Verdict gives the analyst"
            tone="accent"
            items={[
              'Every answer is checked before the analyst sees it',
              'Only the questions that need a person reach the review queue',
              'The evidence comes with it, not just a number',
            ]}
          />
          <Handshake className="mx-auto block w-full max-w-[40rem]" />
          <GiveList
            title="What the analyst gives Verdict"
            tone="brand"
            items={[
              'Fixes the answers Verdict was unsure about',
              'Teaches meanings, like what "revenue" means here',
              'Every approval helps the next similar question',
            ]}
          />
        </div>
      </section>

      {/* flow diagram */}
      <section id="how" className="pt-16">
        <h2 className="mb-2 text-[2.125rem] font-bold tracking-tight">How a verdict is made</h2>
        <p className="mb-8 text-muted">An example of one question going from the analyst to a checked answer. The numbers in it are only for illustration. Click any step to jump to it.</p>
        <FlowStory />

        <div className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-3">
          <LevelExplain level="trusted" body="Most attempts agree and every check that ran passed. The reasons and the evidence are one click away, so you can see why." />
          <LevelExplain level="review" body="Something is off: attempts disagree, the question has two meanings, or it conflicts with an approved answer. An analyst decides." />
          <LevelExplain level="reject" body="Most attempts failed, or the data does not contain what the question needs. Verdict says what is missing." />
        </div>
      </section>

      {/* tested numbers: empty until results.json exists */}
      <section className="pt-24">
        <h2 className="mb-2 text-[2.125rem] font-bold tracking-tight">Tested, not guessed</h2>
        <p className="mb-8 text-muted">These will come from the full evaluation on held-out questions, each with a range. Until it has run, they stay empty.</p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <PendingStat label="How often Trusted was right" />
          <PendingStat label="Questions that needed no human" />
          <PendingStat label="Unanswerable questions caught" />
        </div>
      </section>

      <section className="mt-24 flex flex-wrap items-center justify-between gap-5 rounded-3xl bg-brand p-10 text-on-brand">
        <h3 className="max-w-[45rem] text-[1.75rem] font-bold leading-tight">
          AI can write the query. Verdict tells you whether to trust the answer.
        </h3>
        <Link to="/ask" className={`${BTN} border-transparent bg-accent text-on-accent`}>
          Open Verdict <span aria-hidden>&rarr;</span>
        </Link>
      </section>
      </div>
    </div>
  )
}

// Blue light and a faint grid behind the whole page. Decoration only.
function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      <div className="absolute inset-x-0 top-0 h-[87.5rem] bg-[radial-gradient(60%_50%_at_12%_8%,rgba(21,88,201,.45),transparent_70%),radial-gradient(45%_55%_at_82%_38%,rgba(21,88,201,.55),transparent_70%),radial-gradient(70%_40%_at_50%_100%,rgba(21,88,201,.25),transparent_70%)]" />
      <div className="absolute inset-x-0 top-0 h-[68.75rem] bg-[linear-gradient(rgba(91,141,239,.10)_1px,transparent_1px),linear-gradient(90deg,rgba(91,141,239,.10)_1px,transparent_1px)] bg-[size:64px_64px] [mask-image:radial-gradient(70%_70%_at_50%_35%,#000_30%,transparent_80%)]" />
      <div className="absolute top-[-12.5rem] left-[82%] h-[56.25rem] w-[0.125rem] rotate-[24deg] bg-gradient-to-b from-transparent via-brand-text/50 to-transparent blur-[0.0625rem]" />
      <div className="absolute top-[-9.375rem] left-[88%] h-[50rem] w-px rotate-[24deg] bg-gradient-to-b from-transparent via-brand-text/30 to-transparent" />
      <div className="absolute top-[93.75rem] left-1/2 h-[43.75rem] w-[75rem] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgba(21,88,201,.28),transparent)]" />
    </div>
  )
}

function GiveList({ title, items, tone }: { title: string; items: string[]; tone: 'accent' | 'brand' }) {
  const dot = tone === 'accent' ? 'bg-accent' : 'bg-brand-text'
  const border = tone === 'accent' ? 'border-accent/40' : 'border-brand/50'
  return (
    <div className={`rounded-2xl border ${border} bg-surface/70 p-6 backdrop-blur`}>
      <h3 className="mb-4 text-lg font-bold">{title}</h3>
      <ul className="space-y-3">
        {items.map((t) => (
          <li key={t} className="flex gap-3 text-sm leading-relaxed text-muted">
            <span className={`mt-[0.45rem] h-2 w-2 shrink-0 rounded-full ${dot}`} />
            {t}
          </li>
        ))}
      </ul>
    </div>
  )
}

function LevelExplain({ level, body }: { level: 'trusted' | 'review' | 'reject'; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-line p-5">
      <div className="mb-3"><LevelBadge level={level} stamp /></div>
      <p className="text-sm leading-relaxed text-muted">{body}</p>
    </div>
  )
}

function PendingStat({ label }: { label: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-6">
      <div className="mb-2 font-mono text-4xl font-bold text-muted">--</div>
      <div className="mb-1 font-semibold">{label}</div>
      <div className="text-xs text-muted">Not measured yet</div>
    </div>
  )
}
