// Every call to the backend goes through here. Shapes follow docs/API.md.
// There is no mock: every call goes to the real server.
// Locally the server is the same origin (http://localhost:8000, or the Vite proxy in dev).
// For a deployment where the API lives elsewhere, build with VITE_API_BASE=https://api.example.com.

import type {
  AdminUserRow,
  ArenaRunResponse,
  ArenaScore,
  AskEvent,
  AskResponse,
  AskSummary,
  AuthResponse,
  DatabaseInfo,
  DatabaseSchema,
  Knowledge,
  LedgerEntry,
  Me,
  Meaning,
  ModelInfo,
  ResolveBody,
  ReviewDetail,
  ReviewItem,
  ReviewList,
  SavedItem,
  Settings,
  SqlRunResult,
  UploadResult,
} from './types'

const BASE = String(import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '')

// The login token. The backend reads it from the Authorization header.
const TOKEN_KEY = 'verdict.token'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t)
  else localStorage.removeItem(TOKEN_KEY)
}

// Carries the HTTP status, so screens can tell 401, 402, 403, 429, 503 and 504 apart.
// The message is the server's own "detail" text, shown to the user as it is.
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}, json = true): Promise<T> {
  const token = getToken()
  const res = await fetch(`${BASE}/api${path}`, {
    ...init,
    headers: {
      ...(json ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  })
  if (!res.ok) {
    let msg = ''
    try {
      const body = await res.json()
      const d = body?.detail
      msg = typeof d === 'string' ? d : typeof d?.message === 'string' ? d.message : d ? JSON.stringify(d) : ''
    } catch {
      msg = res.statusText
    }
    const err = new ApiError(res.status, msg || `Request failed (${res.status})`)
    // 401: the token is gone or expired. Drop it; the app then shows the login page.
    if (res.status === 401 && getToken()) {
      setToken(null)
      window.dispatchEvent(new Event('verdict:logout'))
    }
    throw err
  }
  return res.json() as Promise<T>
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
const put = <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) })
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })
const q = (v: string) => encodeURIComponent(v)

export const api = {
  // accounts and credits
  login: (email: string, password: string) => post<AuthResponse>('/auth/login', { email, password }),
  signup: (name: string, email: string, password: string) => post<AuthResponse>('/auth/signup', { name, email, password }),
  async logout(): Promise<void> {
    await post('/auth/logout').catch(() => undefined)
    setToken(null)
  },
  me: () => get<Me>('/me'),
  myUsage: () => get<LedgerEntry[]>('/me/usage'),

  // provider (admin only)
  adminUsers: () => get<AdminUserRow[]>('/admin/users'),
  adminUsage: (userId: string) => get<LedgerEntry[]>(`/admin/users/${q(userId)}/usage`),
  adminCredits: (userId: string, amount: number, note: string) => post<AdminUserRow>(`/admin/users/${q(userId)}/credits`, { amount, note }),
  adminSetActive: (userId: string, active: boolean) => post<AdminUserRow>(`/admin/users/${q(userId)}/active`, { active }),

  // asks; ask costs prices.ask credits (402 when there are not enough)
  ask: (question: string, databaseId: string) => post<AskResponse>('/ask', { question, database_id: databaseId }),
  recentAsks: (limit = 20) => get<AskSummary[]>(`/asks?limit=${limit}`),
  getAsk: (id: string) => get<AskResponse>(`/asks/${q(id)}`),
  askEvents: (id: string) => get<AskEvent[]>(`/asks/${q(id)}/events`),
  flagAsk: (id: string, note: string) => post<{ ok: true; review_id: string }>(`/asks/${q(id)}/flag`, { note }),
  chooseOption: (id: string, option: number, saveMeaning?: { term: string; definition: string }) =>
    post<ReviewItem>(`/asks/${q(id)}/choose`, { option, save_meaning: saveMeaning }),

  // review queue
  reviewList: (status: 'open' | '' = 'open') => get<ReviewList>(`/review?status=${status}`),
  reviewGet: (id: string) => get<ReviewDetail>(`/review/${q(id)}`),
  resolve: (id: string, body: ResolveBody) => post<ReviewDetail>(`/review/${q(id)}/resolve`, body),

  // SQL
  runSql: (sql: string, databaseId: string) => post<SqlRunResult>('/sql/run', { database_id: databaseId, sql }),

  // databases, models, settings
  databases: () => get<DatabaseInfo[]>('/databases'),
  schema: (id: string) => get<DatabaseSchema>(`/databases/${q(id)}/schema`),
  upload(file: File): Promise<UploadResult> {
    const form = new FormData()
    form.append('file', file)
    return request<UploadResult>('/databases/upload', { method: 'POST', body: form }, false)
  },
  models: () => get<ModelInfo[]>('/models'),
  settings: () => get<Settings>('/settings'),
  saveSettings: (s: Partial<Settings>) => put<Settings>('/settings', s), // admin only

  // knowledge; delete is admin only
  knowledge: (databaseId: string) => get<Knowledge>(`/knowledge?database_id=${q(databaseId)}`),
  addMeaning: (m: { term: string; definition: string; sql_hint?: string }, databaseId: string) =>
    post<Meaning>('/knowledge/meanings', { database_id: databaseId, ...m }),
  deleteKnowledge: (kind: 'meanings' | 'examples' | 'known', id: string) => del<{ ok: true }>(`/knowledge/${kind}/${q(id)}`),
  recheckKnown: (id: string) =>
    post<{ ok: boolean; changed: boolean; saved_value: unknown; value_now: unknown; result: SqlRunResult }>(`/knowledge/known/${q(id)}/recheck`),

  // saved answers; rerun costs prices.ask
  saved: () => get<SavedItem[]>('/saved'),
  save: (askId: string, name: string) => post<SavedItem>('/saved', { ask_id: askId, name }),
  deleteSaved: (id: string) => del<{ ok: true }>(`/saved/${q(id)}`),
  rerunSaved: (id: string) => post<SavedItem>(`/saved/${q(id)}/rerun`),

  // proof pages and the Model Arena
  results: () => get<Record<string, unknown>>('/results'), // 404 until the evaluation writes results.json
  arenaScores: () => get<ArenaScore[]>('/arena/models'),
  arenaKeys: () => get<string[]>('/arena'),
  arenaCached: (key: string) => get<unknown>(`/arena/${q(key)}`), // shape not fixed in docs/API.md yet
  // own model free, each outside model costs prices.arena_outside_model; 402 before anything runs
  arenaRun: (question: string, models: string[], databaseId: string) =>
    post<ArenaRunResponse>('/arena/run', { question, database_id: databaseId, models }),
}

// Tell other parts of the page (review count, credits) that something changed.
export function notifyChanged() {
  window.dispatchEvent(new Event('verdict:changed'))
}
