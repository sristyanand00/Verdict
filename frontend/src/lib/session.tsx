// Who is logged in, and their credits. Loaded once from GET /api/me, refreshed after every
// change (an ask uses credits) and cleared when the server says the login is no longer valid.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken } from './api'
import type { Me } from './types'

type Session = {
  me: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (name: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const Ctx = createContext<Session | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setMe(null)
      return
    }
    try {
      setMe(await api.me())
    } catch {
      setMe(null)
    }
  }, [])

  useEffect(() => {
    refresh().finally(() => setLoading(false))
    const drop = () => setMe(null)
    const reload = () => void refresh()
    window.addEventListener('verdict:logout', drop)
    window.addEventListener('verdict:changed', reload)
    return () => {
      window.removeEventListener('verdict:logout', drop)
      window.removeEventListener('verdict:changed', reload)
    }
  }, [refresh])

  const value: Session = {
    me,
    loading,
    refresh,
    async login(email, password) {
      const r = await api.login(email, password)
      setToken(r.token)
      setMe(r.me)
    },
    async signup(name, email, password) {
      const r = await api.signup(name, email, password)
      setToken(r.token)
      setMe(r.me)
    },
    async logout() {
      await api.logout()
      setMe(null)
    },
  }

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useSession(): Session {
  const s = useContext(Ctx)
  if (!s) throw new Error('useSession must be used inside SessionProvider')
  return s
}
