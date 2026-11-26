// Which database the analyst is working on. The list comes from GET /api/databases (never hard-coded).
// The choice is kept in localStorage. Without a saved choice, the server's default
// (GET /api/settings) is used, or else the first database that is available.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'
import type { DatabaseInfo } from './types'

const KEY = 'verdict.database'

type DatabaseState = {
  databases: DatabaseInfo[] | null
  current: DatabaseInfo | null
  error: string | null
  choose: (id: string) => void
  reload: () => Promise<void>
}

const Ctx = createContext<DatabaseState | null>(null)

export function DatabaseProvider({ children }: { children: ReactNode }) {
  const [databases, setDatabases] = useState<DatabaseInfo[] | null>(null)
  const [currentId, setCurrentId] = useState<string | null>(() => localStorage.getItem(KEY))
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const list = await api.databases()
      setDatabases(list)
      setError(null)
      const usable = (id: string | null) => !!id && list.some((d) => d.id === id && d.available)
      const saved = localStorage.getItem(KEY)
      if (usable(saved)) {
        setCurrentId(saved)
        return
      }
      const fallback = await api
        .settings()
        .then((s) => s.database_id)
        .catch(() => null)
      setCurrentId(usable(fallback) ? fallback : (list.find((d) => d.available)?.id ?? null))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the databases')
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const choose = useCallback((id: string) => {
    localStorage.setItem(KEY, id)
    setCurrentId(id)
  }, [])

  const current = databases?.find((d) => d.id === currentId) ?? null

  return <Ctx.Provider value={{ databases, current, error, choose, reload }}>{children}</Ctx.Provider>
}

export function useDatabase(): DatabaseState {
  const s = useContext(Ctx)
  if (!s) throw new Error('useDatabase must be used inside DatabaseProvider')
  return s
}
