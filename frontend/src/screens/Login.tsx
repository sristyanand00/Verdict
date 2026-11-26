// Log in and sign up. One page, two modes (/login and /signup).
// After logging in the user goes back to the page they tried to open, or to Ask.

import { useState, type FormEvent, type InputHTMLAttributes } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { useSession } from '../lib/session'

export default function Login({ mode }: { mode: 'login' | 'signup' }) {
  const { me, login, signup } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/ask'

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (me) return <Navigate to={from} replace />

  const signingUp = mode === 'signup'

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (signingUp) await signup(name, email, password)
      else await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reach the server.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <Logo />
        <h1 className="mt-10 text-2xl font-semibold">{signingUp ? 'Create your account' : 'Log in'}</h1>
        <p className="mt-1 text-sm text-muted">
          {signingUp ? 'Each question you ask uses credits from your account.' : 'Use the account your provider gave you, or create one.'}
        </p>

        <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-4">
          {signingUp && <Field label="Name" value={name} onChange={setName} autoComplete="name" required />}
          <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" required />
          <Field
            label="Password"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete={signingUp ? 'new-password' : 'current-password'}
            minLength={signingUp ? 8 : undefined}
            required
          />
          {error && <p className="text-sm text-lv-red">{error}</p>}
          <button type="submit" disabled={busy} className="mt-2 rounded-md bg-brand px-4 py-2.5 text-sm font-semibold text-on-brand disabled:opacity-50">
            {busy ? 'Please wait...' : signingUp ? 'Create account' : 'Log in'}
          </button>
        </form>

        <p className="mt-6 text-sm text-muted">
          {signingUp ? (
            <>Already have an account? <Link to="/login" state={location.state} className="text-brand-text hover:underline">Log in</Link></>
          ) : (
            <>New here? <Link to="/signup" state={location.state} className="text-brand-text hover:underline">Create an account</Link></>
          )}
        </p>

      </div>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  ...rest
}: { label: string; value: string; onChange: (v: string) => void } & Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'>) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="text-muted">{label}</span>
      <input
        {...rest}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-line bg-surface px-3 py-2 text-ink focus:border-brand focus:outline-none"
      />
    </label>
  )
}
