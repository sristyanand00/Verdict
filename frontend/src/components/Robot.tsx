// Original robot drawings for the Model Arena, one look per model:
//   base = boxy grey robot (untrained)
//   sft  = cobalt robot with glasses and a book (trained on examples)
//   grpo = the Verdict robot: round, cute and lime (trained against the checker)
// mood changes the face: idle, thinking, correct, wrong.

export type RobotKind = 'cloud' | 'base' | 'sft' | 'grpo'
export type RobotMood = 'idle' | 'thinking' | 'correct' | 'wrong'

const PALETTE: Record<RobotKind, { body: string; shade: string; joint: string; line: string; eye: string }> = {
  cloud: { body: '#e9eef5', shade: '#c9d2df', joint: '#8e9aab', line: '#5b6577', eye: '#7fb2ff' },
  base: { body: '#a3a9b2', shade: '#868c95', joint: '#646a73', line: '#4a4f57', eye: '#b8c4d6' },
  sft: { body: '#3a78e0', shade: '#2a5fbc', joint: '#1c468f', line: '#12305f', eye: '#a9c6ff' },
  grpo: { body: '#d4ff24', shade: '#b2d81a', joint: '#88a612', line: '#5f750b', eye: '#ffffff' },
}

const VISOR = '#0b0f1a'

function Eyes({ kind, mood, cx, cy, gap, r }: { kind: RobotKind; mood: RobotMood; cx: number; cy: number; gap: number; r: number }) {
  const p = PALETTE[kind]
  const xs = [cx - gap, cx + gap]

  if (mood === 'correct') {
    return (
      <>
        {xs.map((x) => (
          <path key={x} d={`M${x - r} ${cy + r * 0.4} Q${x} ${cy - r * 1.1} ${x + r} ${cy + r * 0.4}`} fill="none" stroke={kind === 'grpo' ? '#d4ff24' : p.eye} strokeWidth={r * 0.45} strokeLinecap="round" />
        ))}
      </>
    )
  }
  if (mood === 'wrong') {
    return (
      <>
        {xs.map((x) => (
          <g key={x} stroke="#f85149" strokeWidth={r * 0.35} strokeLinecap="round">
            <line x1={x - r * 0.7} y1={cy - r * 0.7} x2={x + r * 0.7} y2={cy + r * 0.7} />
            <line x1={x + r * 0.7} y1={cy - r * 0.7} x2={x - r * 0.7} y2={cy + r * 0.7} />
          </g>
        ))}
      </>
    )
  }

  const look = mood === 'thinking' ? 'anim-look' : ''
  if (kind === 'cloud') {
    // glowing oval eyes
    return (
      <g className="anim-blink">
        {xs.map((x) => <ellipse key={x} cx={x} cy={cy} rx={r * 0.8} ry={r} fill={p.eye} />)}
        <g className={look}>
          {xs.map((x) => <circle key={x} cx={x + 1} cy={cy - r * 0.3} r={r * 0.3} fill="#ffffff" />)}
        </g>
      </g>
    )
  }
  if (kind === 'base') {
    // square, dim eyes
    return (
      <g className="anim-blink">
        {xs.map((x) => (
          <rect key={x} x={x - r} y={cy - r * 0.8} width={r * 2} height={r * 1.6} rx={3} fill={p.eye} opacity={0.85} />
        ))}
        <g className={look}>
          {xs.map((x) => <rect key={x} x={x - r * 0.35} y={cy - r * 0.35} width={r * 0.7} height={r * 0.7} rx={1} fill={VISOR} />)}
        </g>
      </g>
    )
  }
  if (kind === 'sft') {
    // round eyes behind glasses
    return (
      <>
        <g className="anim-blink">
          {xs.map((x) => <circle key={x} cx={x} cy={cy} r={r} fill={p.eye} />)}
          <g className={look}>
            {xs.map((x) => <circle key={x} cx={x} cy={cy + 2} r={r * 0.45} fill={VISOR} />)}
          </g>
        </g>
        {xs.map((x) => <circle key={`g${x}`} cx={x} cy={cy} r={r + 4} fill="none" stroke="#e8ecf2" strokeWidth={2.2} />)}
        <line x1={xs[0] + r + 4} y1={cy} x2={xs[1] - r - 4} y2={cy} stroke="#e8ecf2" strokeWidth={2.2} />
      </>
    )
  }
  // grpo: big, sparkly, cute
  return (
    <g className="anim-blink">
      {xs.map((x) => <circle key={x} cx={x} cy={cy} r={r} fill={p.eye} />)}
      <g className={look}>
        {xs.map((x) => (
          <g key={x}>
            <circle cx={x} cy={cy + 1} r={r * 0.58} fill="#14213d" />
            <circle cx={x + r * 0.22} cy={cy - r * 0.25} r={r * 0.22} fill="#ffffff" />
            <circle cx={x - r * 0.22} cy={cy + r * 0.25} r={r * 0.1} fill="#ffffff" />
          </g>
        ))}
      </g>
    </g>
  )
}

function Mouth({ mood, x, y, color }: { mood: RobotMood; x: number; y: number; color: string }) {
  if (mood === 'correct') return <path d={`M${x - 10} ${y} Q${x} ${y + 11} ${x + 10} ${y}`} fill="none" stroke={color} strokeWidth={3} strokeLinecap="round" />
  if (mood === 'wrong') return <path d={`M${x - 9} ${y + 6} Q${x} ${y - 3} ${x + 9} ${y + 6}`} fill="none" stroke="#f85149" strokeWidth={3} strokeLinecap="round" />
  if (mood === 'thinking') return <circle cx={x} cy={y + 3} r={3.5} fill="none" stroke={color} strokeWidth={2.5} />
  return <path d={`M${x - 7} ${y + 1} Q${x} ${y + 6} ${x + 7} ${y + 1}`} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" />
}

function BaseBot({ mood }: { mood: RobotMood }) {
  const p = PALETTE.base
  return (
    <>
      {/* legs */}
      <rect x={76} y={198} width={18} height={34} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      <rect x={106} y={198} width={18} height={34} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      <rect x={66} y={228} width={36} height={16} rx={3} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <rect x={98} y={228} width={36} height={16} rx={3} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      {/* arms */}
      <rect x={38} y={140} width={18} height={50} rx={3} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <rect x={144} y={140} width={18} height={50} rx={3} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <rect x={36} y={188} width={22} height={14} rx={3} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      <rect x={142} y={188} width={22} height={14} rx={3} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      {/* torso */}
      <rect x={90} y={120} width={20} height={14} fill={p.joint} />
      <rect x={56} y={132} width={88} height={70} rx={8} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      {[[62, 138], [138, 138], [62, 196], [138, 196]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r={2.5} fill={p.joint} />)}
      <rect x={76} y={148} width={48} height={32} rx={4} fill={VISOR} stroke={p.line} />
      <circle cx={90} cy={164} r={8} fill="none" stroke={p.eye} strokeWidth={2} />
      <line x1={90} y1={164} x2={95} y2={159} stroke={p.eye} strokeWidth={2} />
      <rect x={104} y={156} width={14} height={4} rx={1} fill={p.eye} opacity={0.6} />
      <rect x={104} y={166} width={10} height={4} rx={1} fill={p.eye} opacity={0.6} />
      {/* head */}
      <line x1={100} y1={34} x2={100} y2={14} stroke={p.line} strokeWidth={3} />
      <circle cx={100} cy={11} r={6} fill={mood === 'thinking' ? '#e3b341' : p.joint} />
      <rect x={38} y={66} width={12} height={26} rx={3} fill={p.joint} />
      <rect x={150} y={66} width={12} height={26} rx={3} fill={p.joint} />
      <rect x={48} y={34} width={104} height={88} rx={12} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <rect x={60} y={50} width={80} height={48} rx={8} fill={VISOR} stroke={p.line} strokeWidth={1.5} />
      <Eyes kind="base" mood={mood} cx={100} cy={72} gap={20} r={9} />
      {[0, 1, 2, 3, 4].map((i) => <line key={i} x1={82 + i * 9} y1={106} x2={82 + i * 9} y2={114} stroke={p.line} strokeWidth={2.5} strokeLinecap="round" />)}
    </>
  )
}

function SftBot({ mood }: { mood: RobotMood }) {
  const p = PALETTE.sft
  return (
    <>
      <rect x={78} y={196} width={16} height={34} rx={8} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      <rect x={106} y={196} width={16} height={34} rx={8} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      <rect x={66} y={226} width={34} height={18} rx={9} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <rect x={100} y={226} width={34} height={18} rx={9} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      {/* arms bent to hold the book */}
      <g transform="translate(60 148) rotate(-22)"><rect x={-9} y={-4} width={18} height={38} rx={9} fill={p.body} stroke={p.line} strokeWidth={1.5} /></g>
      <g transform="translate(140 148) rotate(22)"><rect x={-9} y={-4} width={18} height={38} rx={9} fill={p.body} stroke={p.line} strokeWidth={1.5} /></g>
      <rect x={91} y={122} width={18} height={14} rx={4} fill={p.joint} />
      <rect x={58} y={132} width={84} height={72} rx={28} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <rect x={62} y={188} width={76} height={10} rx={5} fill={p.shade} />
      <circle cx={60} cy={148} r={11} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      <circle cx={140} cy={148} r={11} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      {/* book */}
      <g transform="rotate(-4 100 180)">
        <path d="M70 162 L100 168 L130 162 L130 196 L100 202 L70 196 Z" fill="#e8ecf2" stroke={p.line} strokeWidth={1.2} />
        <path d="M74 165 L99 170 L99 197 L74 192 Z" fill="#ffffff" />
        <path d="M101 170 L126 165 L126 192 L101 197 Z" fill="#ffffff" />
        {[0, 1, 2].map((i) => (
          <g key={i} stroke="#9aa3b2" strokeWidth={1.5}>
            <line x1={78} y1={175 + i * 6} x2={95} y2={178 + i * 6} />
            <line x1={105} y1={178 + i * 6} x2={122} y2={175 + i * 6} />
          </g>
        ))}
      </g>
      <circle cx={83} cy={180} r={10} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <circle cx={117} cy={180} r={10} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      {/* head */}
      <line x1={72} y1={34} x2={66} y2={12} stroke={p.line} strokeWidth={3} strokeLinecap="round" />
      <line x1={128} y1={34} x2={134} y2={12} stroke={p.line} strokeWidth={3} strokeLinecap="round" />
      <circle cx={66} cy={10} r={5} fill={mood === 'thinking' ? '#a9c6ff' : p.joint} />
      <circle cx={134} cy={10} r={5} fill={mood === 'thinking' ? '#a9c6ff' : p.joint} />
      <circle cx={40} cy={80} r={13} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      <circle cx={160} cy={80} r={13} fill={p.joint} stroke={p.line} strokeWidth={1.2} />
      <rect x={40} y={30} width={120} height={95} rx={40} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <ellipse cx={76} cy={44} rx={20} ry={6} fill="#ffffff" opacity={0.25} />
      <rect x={54} y={52} width={92} height={56} rx={24} fill={VISOR} stroke={p.line} strokeWidth={1.5} />
      <Eyes kind="sft" mood={mood} cx={100} cy={76} gap={19} r={9} />
      <Mouth mood={mood} x={100} y={96} color={p.eye} />
    </>
  )
}

function CloudBot({ mood }: { mood: RobotMood }) {
  const p = PALETTE.cloud
  const signal = mood === 'thinking' ? 'anim-twinkle' : ''
  return (
    <>
      {/* legs */}
      <rect x={80} y={196} width={15} height={32} rx={7} fill={p.joint} />
      <rect x={105} y={196} width={15} height={32} rx={7} fill={p.joint} />
      <rect x={68} y={226} width={32} height={18} rx={9} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <rect x={100} y={226} width={32} height={18} rx={9} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      {/* arms */}
      <g transform="translate(62 148) rotate(14)"><rect x={-8} y={-4} width={16} height={44} rx={8} fill={p.body} stroke={p.line} strokeWidth={1.5} /></g>
      <g transform="translate(138 148) rotate(-14)"><rect x={-8} y={-4} width={16} height={44} rx={8} fill={p.body} stroke={p.line} strokeWidth={1.5} /></g>
      {/* body */}
      <rect x={92} y={122} width={16} height={14} rx={4} fill={p.joint} />
      <rect x={60} y={132} width={80} height={70} rx={24} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <rect x={64} y={186} width={72} height={9} rx={4.5} fill={p.shade} />
      <rect x={80} y={148} width={40} height={30} rx={9} fill={VISOR} />
      {/* wifi mark on the chest */}
      <g fill="none" stroke={p.eye} strokeWidth={2.4} strokeLinecap="round">
        <path d="M90 162 Q100 154 110 162" />
        <path d="M94 166 Q100 161 106 166" />
      </g>
      <circle cx={100} cy={170} r={2.2} fill={p.eye} />
      {/* head */}
      <line x1={100} y1={32} x2={100} y2={22} stroke={p.line} strokeWidth={3} strokeLinecap="round" />
      <circle cx={42} cy={78} r={12} fill={p.joint} />
      <circle cx={158} cy={78} r={12} fill={p.joint} />
      <rect x={42} y={30} width={116} height={94} rx={44} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <ellipse cx={76} cy={44} rx={20} ry={6} fill="#ffffff" opacity={0.6} />
      <rect x={56} y={52} width={88} height={54} rx={26} fill={VISOR} stroke={p.line} strokeWidth={1.5} />
      <Eyes kind="cloud" mood={mood} cx={100} cy={76} gap={20} r={10} />
      <Mouth mood={mood} x={100} y={95} color={p.eye} />
      {/* the cloud it talks to */}
      <g className={signal}>
        <path d="M88 14 Q100 6 112 14" fill="none" stroke={p.eye} strokeWidth={2} strokeLinecap="round" strokeDasharray="3 4" />
      </g>
      <path
        d="M78 2 a12 12 0 0 1 10 -16 a16 16 0 0 1 28 -4 a12 12 0 0 1 12 20 z"
        fill="#ffffff"
        stroke={p.line}
        strokeWidth={1.5}
        transform="translate(-3 -6)"
      />
    </>
  )
}

function GrpoBot({ mood }: { mood: RobotMood }) {
  const p = PALETTE.grpo
  const armUp = mood === 'correct'
  return (
    <>
      {/* stubby legs */}
      <rect x={82} y={194} width={15} height={26} rx={7} fill={p.joint} />
      <rect x={103} y={194} width={15} height={26} rx={7} fill={p.joint} />
      <ellipse cx={88} cy={228} rx={19} ry={11} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <ellipse cx={112} cy={228} rx={19} ry={11} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      {/* little arms */}
      <g transform={`translate(66 156) rotate(${24})`}><rect x={-8} y={-4} width={16} height={32} rx={8} fill={p.body} stroke={p.line} strokeWidth={1.5} /></g>
      <g transform={`translate(134 156) rotate(${armUp ? -150 : -24})`}><rect x={-8} y={-4} width={16} height={32} rx={8} fill={p.body} stroke={p.line} strokeWidth={1.5} /></g>
      {/* chubby body */}
      <rect x={64} y={136} width={72} height={64} rx={30} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <ellipse cx={100} cy={190} rx={28} ry={6} fill={p.shade} />
      <circle cx={100} cy={166} r={15} fill={VISOR} />
      <path d="M92 166 L98 172 L109 160" fill="none" stroke={p.body} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />
      {/* big round head */}
      <line x1={100} y1={22} x2={100} y2={6} stroke={p.line} strokeWidth={3} strokeLinecap="round" />
      <path d="M100 -6 l3 6 6 2 -6 2 -3 6 -3 -6 -6 -2 6 -2z" fill={p.body} stroke={p.line} strokeWidth={1.2} className={mood === 'thinking' ? 'anim-twinkle' : ''} />
      <circle cx={34} cy={80} r={12} fill={p.joint} />
      <circle cx={166} cy={80} r={12} fill={p.joint} />
      <rect x={34} y={20} width={132} height={118} rx={58} fill={p.body} stroke={p.line} strokeWidth={1.5} />
      <ellipse cx={72} cy={38} rx={22} ry={7} fill="#ffffff" opacity={0.45} />
      <rect x={50} y={46} width={100} height={70} rx={33} fill={VISOR} stroke={p.line} strokeWidth={1.5} />
      <Eyes kind="grpo" mood={mood} cx={100} cy={78} gap={22} r={14} />
      <ellipse cx={66} cy={98} rx={7} ry={4} fill="#ff8fb1" opacity={0.7} />
      <ellipse cx={134} cy={98} rx={7} ry={4} fill="#ff8fb1" opacity={0.7} />
      <Mouth mood={mood} x={100} y={100} color={p.body} />
    </>
  )
}

export function Robot({ kind, mood = 'idle', className = '', title }: { kind: RobotKind; mood?: RobotMood; className?: string; title?: string }) {
  const motion = mood === 'thinking' ? 'anim-think' : mood === 'correct' ? 'anim-hop' : mood === 'wrong' ? 'anim-shake' : 'anim-float'
  return (
    <svg viewBox="0 -12 210 272" className={`overflow-visible ${className}`} role="img" aria-label={title}>
      <ellipse cx={100} cy={250} rx={50} ry={6} fill="#000" opacity={0.3} />
      <g key={mood} className={motion}>
        {kind === 'cloud' && <CloudBot mood={mood} />}
        {kind === 'base' && <BaseBot mood={mood} />}
        {kind === 'sft' && <SftBot mood={mood} />}
        {kind === 'grpo' && <GrpoBot mood={mood} />}
      </g>
    </svg>
  )
}
