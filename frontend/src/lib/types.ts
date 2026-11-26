// Shapes of the API responses the frontend uses.
// Source of truth: docs/API.md (owned by the Backend chat). If it changes, change it here.
// Fields marked "proposed" are in plan section 8 but not in API.md yet, so they are optional.

export type Level = 'trusted' | 'review' | 'reject'

export type Reason = {
  // not_in_data, two_meanings, failed, low_agreement, agreement, empty, conflict, second_model, not_empty
  code: string
  text: string
}

// off: the check did not run. info: a fact, not evidence about this answer (never a green tick).
export type CheckStatus = 'pass' | 'fail' | 'off' | 'info'

export type Check = {
  key: string // safe, ran, agreement, not_empty, no_split, known_numbers, second_model
  name: string
  status: CheckStatus
  detail: string
}

export type Group = {
  size: number
  sql: string
  columns: string[]
  preview: unknown[][]
  row_count: number
  empty: boolean
}

export type Attempt = {
  index: number
  kind: 'sql' | 'cannot_answer' | 'empty'
  sql: string | null
  status: 'ok' | 'blocked' | 'timeout' | 'error' | 'crashed' | null
  error: string | null
  group: number | null
}

export type MeaningOption = {
  label: string
  sql: string
  columns: string[]
  rows: unknown[][]
  size: number
  answer_text: string | null
}

export type TestedTrust = {
  precision: number
  low: number
  high: number
  on: string
}

// proposed: where the number came from, read only from the SQL
export type Lineage = {
  output: string
  formula: string
  tables: string[]
  columns: string[]
  filters: string[]
  period: string | null
  group_by: string[]
}

export type AskResponse = {
  ask_id: string
  question: string
  database_id: string
  level: Level
  reasons: Reason[]
  answer_text: string | null
  columns: string[]
  rows: unknown[][]
  row_count: number
  sql: string | null
  groups: Group[]
  attempts: Attempt[]
  n_attempts: number
  n_cannot_answer: number
  n_failed: number
  checks: Check[]
  options: MeaningOption[] | null
  missing: string | null
  tables_available: string[] | null
  knowledge_used: string[]
  tested_trust: TestedTrust | null
  model: string
  model_label: string
  latency_ms: number
  created_at: string
  review_id: string | null
  flagged: boolean
  flag_note: string | null
  lineage?: Lineage | null // proposed
  elapsed_ms?: number // proposed: time the chosen SQL took
  cache_hit?: boolean // answered from the cache; cached_at is when it was first checked
  cached_at?: string | null
}

export type AskSummary = {
  ask_id: string
  database_id: string
  question: string
  level: Level
  answer_text: string | null
  created_at: string
  flagged: boolean
}

// review queue
export type ReviewStatus = 'open' | 'approved' | 'fixed' | 'rejected'

export type ReviewItem = {
  review_id: string
  ask_id: string
  question: string
  database_id: string
  level: Level
  reasons: Reason[]
  source: 'auto' | 'flagged'
  status: ReviewStatus
  created_at: string
  resolved_at: string | null
}

export type ReviewList = {
  items: ReviewItem[]
  open_counts: { review: number; reject: number }
  today: { asked: number; trusted: number; review: number; reject: number }
}

export type ReviewDetail = {
  review_id: string
  source: 'auto' | 'flagged'
  status: ReviewStatus
  final_sql: string | null
  final_columns: string[] | null
  final_rows: unknown[][] | null
  note: string | null
  created_at: string
  resolved_at: string | null
  ask: AskResponse
}

export type ResolveBody = {
  action: 'approve' | 'fix' | 'reject'
  sql?: string
  note?: string
  save_meaning?: { term: string; definition: string; sql_hint?: string }
  save_known_number?: { name: string }
}

export type SqlRunResult = {
  status: 'ok' | 'blocked' | 'timeout' | 'error' | 'crashed'
  columns: string[]
  rows: unknown[][]
  row_count: number
  truncated: boolean
  error: string | null
  elapsed_ms: number
}

// knowledge
export type Meaning = { id: string; database_id: string; term: string; definition: string; sql_hint: string | null; created_at: string }
export type Example = { id: string; database_id: string; question: string; sql: string; columns: string[]; rows: unknown[][]; from_review_id: string | null; created_at: string }
export type KnownNumber = {
  id: string
  database_id: string
  name: string
  question: string
  sql: string
  columns: string[]
  value: unknown
  created_at: string
  last_checked_at: string | null
  last_ok: boolean | null
}
export type Knowledge = { meanings: Meaning[]; examples: Example[]; known_numbers: KnownNumber[] }

// proposed: event log
export type AskEvent = { actor: 'verdict' | 'analyst'; action: string; detail: string | null; created_at: string }

// proposed: saved queries
export type SavedItem = {
  id: string
  ask_id: string
  name: string
  sql: string
  level: Level
  last_value: string | null
  last_run_at: string
  changed: boolean
}

// accounts and credits (proposed, see frontend/ACCOUNTS-API.md; not in docs/API.md yet)
export type Role = 'analyst' | 'admin'

export type User = {
  id: string
  name: string
  email: string
  role: Role
  active: boolean
  created_at: string
}

export type Prices = {
  ask: number // credits for one question on the Ask page (your own model)
  arena_outside_model: number // credits for each outside model in a live Arena run
}

export type Me = {
  user: User
  credits: { balance: number; used_total: number; used_this_month: number }
  prices: Prices
}

export type AuthResponse = { token: string; me: Me }

// remove: the provider took credits back. refund: credits given back because an ask failed on the server.
export type LedgerKind = 'ask' | 'arena' | 'grant' | 'remove' | 'refund'

export type LedgerEntry = {
  id: string
  at: string
  kind: LedgerKind
  amount: number // positive adds credits, negative uses them
  balance_after: number
  ask_id: string | null
  question: string | null
  note: string | null
}

export type AdminUserRow = User & {
  balance: number
  used_total: number
  asks_count: number
  last_active_at: string | null
}

// models and the Model Arena
export type ModelKind = 'own' | 'outside' // own: the user's Qwen model. outside: Gemini and others, Arena only

export type ModelInfo = {
  id: string
  label: string
  kind: ModelKind
  provider: string // how the server reaches it: openai (vLLM or Ollama) or gemini
  private: boolean
  reachable: boolean
}

export type ArenaScore = {
  model_id: string
  label: string
  kind: ModelKind
  benchmark: string
  n_questions: number
  accuracy: number | null // null: not measured yet
  measured_at: string | null
}

export type ArenaRunResult = {
  model_id: string
  label: string
  kind: ModelKind
  provider: string
  status: 'ok' | 'off' | 'error'
  level: Level | null
  reasons: Reason[]
  answer_text: string | null
  sql: string | null
  columns: string[]
  rows: unknown[][] // at most 20
  n_attempts: number
  agree: number // attempts in the largest group
  latency_ms: number
  cache_hit: boolean
  error: string | null
}

export type ArenaRunResponse = {
  question: string
  database_id: string
  credits_charged: number
  results: ArenaRunResult[]
}

// databases and settings
export type DatabaseInfo = {
  id: string
  name: string
  description: string // one line about the data; empty for uploads
  source: 'preloaded' | 'upload'
  available: boolean // false: the file is not on the server yet
  tables_count: number
}

export type DatabaseSchema = {
  id: string
  name: string
  tables: { name: string; row_count: number; columns: { name: string; type: string }[] }[]
}

export type UploadResult = DatabaseInfo & { tables: string[]; columns: unknown }

export type Settings = {
  database_id: string
  model: string
  second_model: boolean | string | null
  second_model_id: string | null
}
