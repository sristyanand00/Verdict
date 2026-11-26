import { Link } from 'react-router-dom'

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 text-[0.9375rem] font-black tracking-[0.22em] text-ink">
      <span className="grid h-[1.625rem] w-[1.625rem] place-items-center rounded-[0.4375rem] bg-brand">
        <svg viewBox="0 0 16 16" className="h-[0.9375rem] w-[0.9375rem]">
          <path d="M3 8.5l3.2 3.2L13 4.8" fill="none" stroke="#d4ff24" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      VERDICT
    </Link>
  )
}
