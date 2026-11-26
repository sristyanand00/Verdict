// Original illustration: the analyst and Verdict shaking hands.
// The top arrow is Verdict checking answers for the analyst,
// the bottom arrow is the analyst teaching Verdict with every fix.

const SKIN = '#d9a27e'
const SKIN_LINE = '#a8714f'
const HAIR = '#1e1a1a'
const BLAZER = '#232a3a'
const BLAZER_LINE = '#3a4458'
const PANTS = '#1b2130'

// A limb drawn as a thick rounded line with an outline.
function Limb({ points, color, outline, width }: { points: string; color: string; outline: string; width: number }) {
  return (
    <>
      <polyline points={points} fill="none" stroke={outline} strokeWidth={width + 3} strokeLinecap="round" strokeLinejoin="round" />
      <polyline points={points} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" />
    </>
  )
}

function Analyst() {
  return (
    <g>
      <ellipse cx={150} cy={386} rx={70} ry={8} fill="#000" opacity={0.3} />
      {/* legs and shoes */}
      <rect x={128} y={285} width={20} height={90} rx={8} fill={PANTS} />
      <rect x={154} y={285} width={20} height={90} rx={8} fill={PANTS} />
      <rect x={120} y={368} width={34} height={14} rx={7} fill="#0e1118" />
      <rect x={150} y={368} width={38} height={14} rx={7} fill="#0e1118" />

      {/* back arm holding a tablet */}
      <Limb points="118,182 106,240 128,262" color={BLAZER} outline={BLAZER_LINE} width={22} />

      {/* body */}
      <rect x={110} y={165} width={80} height={130} rx={30} fill={BLAZER} stroke={BLAZER_LINE} strokeWidth={1.5} />
      <path d="M136 165 L150 204 L164 165 Z" fill="#e8ecf2" />
      <path d="M140 168 L150 228 L160 168" fill="none" stroke="var(--color-accent)" strokeWidth={2} />
      <rect x={141} y={226} width={18} height={23} rx={3} fill="#f2f4f7" />
      <rect x={141} y={226} width={18} height={6} rx={2} fill="var(--color-brand)" />

      {/* tablet with a small bar chart */}
      <g transform="rotate(-12 138 266)">
        <rect x={116} y={240} width={46} height={56} rx={5} fill="#0b0f1a" stroke="#4b5563" strokeWidth={1.5} />
        <rect x={124} y={276} width={6} height={12} rx={1} fill="var(--color-brand-text)" />
        <rect x={134} y={266} width={6} height={22} rx={1} fill="var(--color-brand-text)" />
        <rect x={144} y={258} width={6} height={30} rx={1} fill="var(--color-accent)" />
      </g>
      <circle cx={130} cy={264} r={9} fill={SKIN} stroke={SKIN_LINE} strokeWidth={1} />

      {/* neck and head */}
      <rect x={141} y={138} width={18} height={30} rx={6} fill={SKIN} />
      <circle cx={116} cy={116} r={6} fill={SKIN} stroke={SKIN_LINE} strokeWidth={1} />
      <circle cx={150} cy={112} r={36} fill={SKIN} stroke={SKIN_LINE} strokeWidth={1} />
      <path d="M113 110 Q112 70 152 71 Q192 73 187 114 Q180 92 152 92 Q126 93 113 110 Z" fill={HAIR} />
      {/* glasses */}
      <circle cx={142} cy={113} r={9} fill="none" stroke={HAIR} strokeWidth={2.2} />
      <circle cx={168} cy={113} r={9} fill="none" stroke={HAIR} strokeWidth={2.2} />
      <line x1={151} y1={113} x2={159} y2={113} stroke={HAIR} strokeWidth={2.2} />
      <circle cx={143} cy={114} r={2.6} fill={HAIR} />
      <circle cx={169} cy={114} r={2.6} fill={HAIR} />
      <path d="M146 130 Q156 138 167 129" fill="none" stroke={HAIR} strokeWidth={2.4} strokeLinecap="round" />

      {/* front arm reaching out */}
      <Limb points="182,184 226,226 270,224" color={BLAZER} outline={BLAZER_LINE} width={22} />
      <line x1={262} y1={216} x2={262} y2={233} stroke="#e8ecf2" strokeWidth={5} strokeLinecap="round" />
    </g>
  )
}

function Bot() {
  return (
    <g>
      <ellipse cx={450} cy={386} rx={66} ry={8} fill="#000" opacity={0.3} />
      {/* legs and feet */}
      <rect className="r-joint" x={428} y={282} width={16} height={80} rx={8} />
      <rect className="r-joint" x={456} y={282} width={16} height={80} rx={8} />
      <rect className="r-body" x={414} y={354} width={38} height={22} rx={11} />
      <rect className="r-body" x={448} y={354} width={38} height={22} rx={11} />

      {/* back arm hanging */}
      <Limb points="490,192 506,244 500,278" color="var(--color-robot)" outline="var(--color-robot-line)" width={18} />
      <circle className="r-body" cx={500} cy={284} r={11} />

      {/* body */}
      <rect className="r-joint" x={441} y={158} width={18} height={20} rx={4} />
      <rect className="r-body" x={408} y={172} width={84} height={114} rx={30} />
      <rect className="r-shade" x={412} y={266} width={76} height={10} rx={5} />
      <rect className="r-panel" x={430} y={196} width={40} height={34} rx={10} />
      <path className="r-check" d="M439 213 L447 221 L462 205" />
      <circle className="r-joint" cx={490} cy={190} r={11} />

      {/* head */}
      <line x1={422} y1={66} x2={416} y2={44} stroke="var(--color-robot-line)" strokeWidth={3} strokeLinecap="round" />
      <line x1={478} y1={66} x2={484} y2={44} stroke="var(--color-robot-line)" strokeWidth={3} strokeLinecap="round" />
      <circle className="r-ball on" cx={416} cy={42} r={5} />
      <circle className="r-ball on" cx={484} cy={42} r={5} />
      <circle className="r-joint" cx={390} cy={112} r={13} />
      <circle className="r-joint" cx={510} cy={112} r={13} />
      <rect className="r-body" x={390} y={62} width={120} height={100} rx={46} />
      <ellipse className="r-shine" cx={426} cy={76} rx={20} ry={6} opacity={0.35} />
      <rect className="r-visor" x={404} y={86} width={92} height={56} rx={27} />
      {/* happy eyes */}
      <g filter="url(#hs-glow)">
        <path className="r-line" strokeWidth={5} d="M420 118 Q431 104 442 118" />
        <path className="r-line" strokeWidth={5} d="M458 118 Q469 104 480 118" />
      </g>
      <path className="r-line" strokeWidth={3} d="M438 128 Q450 136 462 128" />

      {/* front arm reaching out */}
      <circle className="r-joint" cx={410} cy={190} r={11} />
      <Limb points="410,192 368,228 322,224" color="var(--color-robot)" outline="var(--color-robot-line)" width={18} />
    </g>
  )
}

function Hands() {
  return (
    <g>
      <circle cx={298} cy={222} r={56} fill="url(#hs-handglow)" />
      {/* robot hand underneath */}
      <rect x={292} y={209} width={40} height={28} rx={13} fill="var(--color-robot)" stroke="var(--color-robot-line)" strokeWidth={1.5} />
      <line x1={300} y1={236} x2={300} y2={230} stroke="var(--color-robot-line)" strokeWidth={1.2} />
      <line x1={310} y1={236} x2={310} y2={230} stroke="var(--color-robot-line)" strokeWidth={1.2} />
      {/* human hand on top */}
      <rect x={264} y={207} width={44} height={30} rx={14} fill={SKIN} stroke={SKIN_LINE} strokeWidth={1.2} />
      <path d="M280 236 L280 229 M290 237 L290 230 M299 236 L299 229" stroke={SKIN_LINE} strokeWidth={1.2} strokeLinecap="round" />
      {/* both thumbs on top */}
      <rect x={286} y={200} width={24} height={11} rx={5.5} fill={SKIN} stroke={SKIN_LINE} strokeWidth={1.2} transform="rotate(-12 298 205)" />
      <rect x={306} y={201} width={20} height={10} rx={5} fill="var(--color-robot)" stroke="var(--color-robot-line)" strokeWidth={1.2} transform="rotate(10 316 206)" />
      {/* sparkles */}
      <path className="r-spark anim-twinkle" d="M298 150 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3z" />
      <path className="r-spark anim-twinkle" style={{ animationDelay: '-.7s' }} d="M262 176 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2z" />
      <path className="r-spark anim-twinkle" style={{ animationDelay: '-1.4s' }} d="M336 172 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2z" />
    </g>
  )
}

function Label({ x, y, text, tone }: { x: number; y: number; text: string; tone: 'accent' | 'brand' }) {
  const w = text.length * 6.6 + 24
  return (
    <g>
      <rect x={x - w / 2} y={y - 13} width={w} height={26} rx={13} fill="var(--color-surface)" stroke={tone === 'accent' ? 'var(--color-accent)' : 'var(--color-brand-text)'} strokeWidth={1.2} />
      <text x={x} y={y + 4.5} textAnchor="middle" fill="var(--color-ink)" style={{ font: '600 12px "Segoe UI", sans-serif' }}>
        {text}
      </text>
    </g>
  )
}

export function Handshake({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 -50 600 470" className={`overflow-visible ${className}`} role="img" aria-label="A data analyst and Verdict shaking hands">
      <defs>
        <radialGradient id="hs-handglow">
          <stop offset="0%" stopColor="#d4ff24" stopOpacity={0.45} />
          <stop offset="45%" stopColor="#1558c9" stopOpacity={0.35} />
          <stop offset="100%" stopColor="#1558c9" stopOpacity={0} />
        </radialGradient>
        <filter id="hs-glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation={2.5} result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <marker id="hs-arrow-accent" viewBox="0 0 10 10" refX={6} refY={5} markerWidth={7} markerHeight={7} orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 Z" fill="var(--color-accent)" />
        </marker>
        <marker id="hs-arrow-brand" viewBox="0 0 10 10" refX={6} refY={5} markerWidth={7} markerHeight={7} orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 Z" fill="var(--color-brand-text)" />
        </marker>
      </defs>

      {/* Verdict -> analyst: checked answers */}
      <path className="flow" d="M430 30 Q300 -60 170 58" fill="none" stroke="var(--color-accent)" strokeWidth={2.5} markerEnd="url(#hs-arrow-accent)" />
      {/* analyst -> Verdict: fixes and approvals */}
      <path className="flow" d="M200 312 Q300 362 400 312" fill="none" stroke="var(--color-brand-text)" strokeWidth={2.5} markerEnd="url(#hs-arrow-brand)" />

      <Analyst />
      <Bot />
      <Hands />

      <Label x={300} y={-14} text="Verdict checks every answer" tone="accent" />
      <Label x={300} y={372} text="The analyst teaches with every fix" tone="brand" />
      <text x={150} y={410} textAnchor="middle" fill="var(--color-muted)" style={{ font: '700 12px "Segoe UI", sans-serif', letterSpacing: '.14em' }}>ANALYST</text>
      <text x={450} y={410} textAnchor="middle" fill="var(--color-muted)" style={{ font: '700 12px "Segoe UI", sans-serif', letterSpacing: '.14em' }}>VERDICT</text>
    </svg>
  )
}
