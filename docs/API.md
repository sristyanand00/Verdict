# Verdict API contract

The frontend builds against this file. Only the backend changes it. If something here does not match what the server returns, the server is wrong. Report it.

- Base path: `/api`. Everything is JSON, except the file upload.
- Errors come back as `{"detail": "..."}` with a normal HTTP status code:
  - 400: bad request
  - 401: not logged in, or the login expired. Drop the token and show the login page.
  - 402: not enough credits (only on routes that cost credits)
  - 403: logged in but not allowed: the account is turned off, or an analyst called an `/admin` route
  - 404: not found. Also returned for another user's ask, review item or saved answer, so ids do not leak.
  - 409: conflict (for example, the item is already resolved, or the email has an account)
  - 422: a field is missing or invalid
  - 429: too many login or signup tries from one address, or too many questions from one user in a minute. Wait a minute.
  - 500: the server failed. An ask that fails this way is not charged.
  - 503: the model is not reachable, or the server is busy with other questions. Not charged. The text never shows server addresses or internal errors.
  - 504: the question took longer than the server's time limit and was stopped. Not charged.
- Live list of routes while the server runs: `http://localhost:8000/docs`.
- Code: `verdict/api/`. Tests: `tests/test_api.py`, `tests/test_accounts.py`.

## Login

- Every route needs `Authorization: Bearer <token>`, except `/api/health`, `/api/auth/*` and the website files.
- A token comes from signup or login and lasts 7 days, or until logout.
- Roles: `analyst` and `admin` (the provider). Signup always makes an `analyst`. The first `admin` is made on server start from `VERDICT_ADMIN_EMAIL` and `VERDICT_ADMIN_PASSWORD` (docs/DEPLOYMENT.md).
- Who sees what:
  - Asks, review items and saved answers belong to the user who made them. An analyst sees only their own. The provider sees all.
  - Knowledge (meanings, examples, known numbers) is shared by everyone using the same database, for now. An approval by one analyst helps the next analyst's question.
  - Settings (`/api/settings`) are shared by everyone, so only the provider can change them (`PUT` is admin only).
  - An uploaded database belongs to the user who uploaded it: only they and the provider see it in `/api/databases` or can use it. For anyone else it is 404.
  - Knowledge can be added by any user of a database, but only the provider deletes it.

## Levels and reasons

There are three levels: `trusted`, `review` and `reject`. Every answer carries a list of reasons. The frontend shows the reason text and can switch on the reason code.

| Code | Level | Meaning |
|---|---|---|
| `not_in_data` | reject | Most attempts said the data cannot answer it. |
| `two_meanings` | review | Attempts split into two big groups. `options` holds both readings. |
| `failed` | reject | Most attempts did not produce a working query. |
| `low_agreement` | reject | Agreement is below the review level. |
| `agreement` | review / trusted | Review: some agree, but not enough. Trusted: the agreement count. |
| `empty` | review | The answer is empty or only NULL. |
| `conflict` | review | Differs from an approved answer to a near-identical question. |
| `second_model` | review / trusted | The second model disagrees (review) or agrees (trusted). |
| `not_empty` | trusted | The answer has values. |

Rules are checked in this order: not in data, two meanings, reject, review, trusted.

## Accounts and credits

| Method and path | Body | Returns |
|---|---|---|
| `POST /api/auth/signup` | `{name, email, password}` | `{token, me}`. 409 if the email has an account (case is ignored). 400 if the password is under 8 characters or the email is not valid. |
| `POST /api/auth/login` | `{email, password}` | `{token, me}`. 401 on a wrong email or password (same message for both). 403 if the account is turned off. |
| `POST /api/auth/logout` | none | `{ok: true}`. Ends the token. |
| `GET /api/me` | | `Me` |
| `GET /api/me/usage` | | `LedgerEntry[]`, newest first |

Login and signup allow 10 tries a minute from one address (429 after that).

Shapes:

```ts
type User = { id: string; name: string; email: string; role: 'analyst' | 'admin'; active: boolean; created_at: string }
type Me = {
  user: User
  credits: { balance: number; used_total: number; used_this_month: number }
  prices: { ask: number; arena_outside_model: number }
}
type LedgerEntry = {
  id: string
  at: string            // ISO time
  kind: 'ask' | 'arena' | 'grant' | 'remove' | 'refund'
  amount: number        // positive adds credits, negative uses them
  balance_after: number
  ask_id: string | null
  question: string | null
  note: string | null
}
type AdminUserRow = User & { balance: number; used_total: number; asks_count: number; last_active_at: string | null }
```

- `used_total` and `used_this_month` count only `ask` and `arena` rows. The month is the calendar month in UTC.
- The balance only changes through a ledger row, so it always equals the sum of the user's ledger.
- A new account starts with `VERDICT_SIGNUP_CREDITS` (default 20), written as a `grant` row with the note "Starting credits".
- Prices come from the server (`VERDICT_PRICE_ASK`, `VERDICT_PRICE_ARENA_OUTSIDE_MODEL`, both default 1).
- What costs credits: `POST /api/ask` and `POST /api/saved/{id}/rerun` (each `prices.ask`, flat, however many attempts run). Review, approve, fix, reject, knowledge, saving and viewing cached Arena results are free.
- The provider's (`admin`) own asks are free and write no ledger row.

## Provider panel (admin only, 403 for analysts)

| Method and path | Body | Returns |
|---|---|---|
| `GET /api/admin/users` | | `AdminUserRow[]`. `last_active_at` is the time of the newest `ask` or `arena` row, or `null`. |
| `GET /api/admin/users/{id}/usage` | | That user's `LedgerEntry[]`, newest first |
| `POST /api/admin/users/{id}/credits` | `{amount, note}` | The updated `AdminUserRow`. `amount` is a whole number, not 0: positive writes a `grant` row, negative a `remove` row. 400 if the balance would go below 0. 404 for an unknown user. |
| `GET /api/admin/cache` | | Cached questions: `[{database_id, question, created_at}]`, newest first |
| `DELETE /api/admin/cache?database_id=` | | `{ok: true, removed}`. Empties the answer cache, for one database or all. |
| `POST /api/admin/users/{id}/active` | `{active}` | The updated `AdminUserRow`. Turning an account off also ends its logins. 400 if the provider turns off their own account. |

## `POST /api/ask`

Costs `prices.ask` credits:

- Before anything runs: if the balance is below the price, the answer is 402 with `detail: "You have no credits left. Ask the provider for more."`. Nothing runs.
- The charge is written when the ask is saved, in the same transaction: one `ask` row with the `ask_id` and the question.
- A `review` or `reject` verdict is a real answer and is charged. A server failure (503, 500) is not charged.
- Two asks sent at the same time cannot take the balance below 0: the second gets 402 if the first already holds the last credit.

Request. `database_id` and `model` are optional. If left out, the current values from `/api/settings` are used.

```json
{ "question": "How many accounts?", "database_id": "financial", "model": "qwen" }
```

Response:

```json
{
  "ask_id": "a_3f9c1e2b7d",
  "question": "How many accounts?",
  "database_id": "financial",
  "level": "trusted",
  "reasons": [ { "code": "agreement", "text": "7 of 8 attempts agree." },
               { "code": "not_empty", "text": "The answer has values." } ],
  "answer_text": "4,500",
  "columns": ["COUNT(*)"],
  "rows": [[4500]],
  "row_count": 1,
  "sql": "SELECT COUNT(*) FROM account",
  "groups": [
    { "size": 7, "sql": "SELECT ...", "columns": ["COUNT(*)"], "preview": [[4500]], "row_count": 1, "empty": false },
    { "size": 1, "sql": "SELECT ...", "columns": ["n"], "preview": [[4499]], "row_count": 1, "empty": false }
  ],
  "attempts": [
    { "index": 0, "kind": "sql", "sql": "SELECT ...", "status": "ok", "error": null, "group": 0 }
  ],
  "n_attempts": 8, "n_cannot_answer": 0, "n_failed": 0,
  "checks": [
    { "key": "safe", "name": "Safe", "status": "info", "detail": "Read-only sandbox, nothing blocked." }
  ],
  "options": null,
  "missing": null,
  "tables_available": null,
  "knowledge_used": ["revenue = SUM(payment_value), delivered only", "Approved example: \"Revenue in 2017?\""],
  "lineage": { "output": "COUNT(*)", "formula": "COUNT(*)", "tables": ["account"], "columns": [],
               "filters": [], "period": null, "group_by": [] },
  "tested_trust": null,
  "agreement_level": "green",
  "model": "qwen",
  "model_label": "Qwen 1.5B (trained), private",
  "latency_ms": 3200,
  "cache_hit": false,
  "cached_at": null,
  "created_at": "2026-11-19T10:15:02+00:00",
  "review_id": null,
  "flagged": false,
  "flag_note": null
}
```

Field notes:

- `answer_text`, `sql`, `columns` and `rows`:
  - Filled for `trusted` and `review`. For review the answer is a draft for the analyst.
  - Empty (`null` or `[]`) for `reject`, and also when `options` is set.
- `rows` holds at most 500 rows. `row_count` is the number of rows in what is sent.
- `attempts[].kind` is `sql`, `cannot_answer` or `empty`. `status` is the verifier result (`ok`, `blocked`, `timeout`, `error` or `crashed`), or `null` when no SQL ran. `group` is an index into `groups`, or `null`.
- `checks` always lists these 7 keys, in this order: `safe`, `ran`, `agreement`, `not_empty`, `no_split`, `known_numbers`, `second_model`.
  - Each `status` is `pass`, `fail`, `off` or `info`.
  - `off` means the check did not run, and `detail` says why. Never show `off` as passed.
  - `info` (added 25 Nov) is a fact, not evidence about this answer. Show it in a neutral style, never as a green tick. Used for:
    - `safe`: always `info`. The sandbox is the same for every question.
    - `no_split`: `info` when `agreement` passed, because a split is then impossible and a tick would count agreement twice. `fail` on a split. `pass` only when agreement failed but the answers did not split into two meanings.
  - `known_numbers` is `off` when no approved answer to a near-identical question exists, so nothing was compared. It is `pass` only after a real comparison.
  - So a Trusted answer with no approved history shows three ticks: `ran`, `agreement`, `not_empty`.
- `options`: only when the reason is `two_meanings`. Each option is `{label, sql, columns, rows, size, answer_text}`.
- `missing` and `tables_available`: only when the reason is `not_in_data`. `missing` is often `null` because the model usually does not say what is missing.
- `tested_trust`: `{precision, low, high, on}` from `results/results.json`. It is `null` until the evaluation step writes that file. Show nothing when it is `null`.
- `lineage` (added 25 Nov): where the answer came from, read only from `sql`, with table aliases replaced by table names. `{output, formula, tables, columns, filters, period, group_by}`. `output` is the result's column names, `formula` the select expressions, `filters` the WHERE and HAVING conditions one by one, `period` the filters on date-like columns joined by "and" (or `null`). It is `null` when no answer is shown or the SQL cannot be read; hide the section then.
- `agreement_level` is the older agreement-only level (`green`, `yellow`, `red` or `unanswerable`). It is kept for evaluation. The frontend can ignore it.
- `cache_hit` and `cached_at` (added 26 Nov): a repeated question (same database, same words ignoring case and spacing, same model and attempts, and no change to that database's knowledge since) is answered from the cache. `cache_hit` is then `true` and `cached_at` is when the answer was first made; show it ("Answered from cache, first checked at ..."). It is still saved as the user's own ask, goes to the review queue if not trusted, and is charged like any answer. Any approval, fix, meaning or known number on that database makes the next ask run fresh.
- `review_id`: anything that is not trusted is added to the review queue, and this is that item's id.

## Asks

The caller's own asks only (the provider sees all). Another user's ask is 404.

| Method and path | Body | Returns |
|---|---|---|
| `GET /api/asks?limit=20&database_id=` | | `[{ask_id, database_id, question, level, answer_text, created_at, flagged}]`, newest first |
| `GET /api/asks/{ask_id}` | | The full `/api/ask` response, plus the current `review_id`, `flagged` and `flag_note` |
| `GET /api/asks/{ask_id}/events` | | The history of the ask, oldest first: `[{actor, action, detail, created_at}]`. `actor` is `verdict` or `analyst`. `action` is `asked`, `flagged`, `chosen`, `approved`, `fixed` or `rejected`. Asks made before 25 Nov have no events. |
| `POST /api/asks/{ask_id}/flag` | `{"note": "..."}` | `{"ok": true, "review_id": "r_..."}`. The analyst says a Trusted answer is wrong, and it goes to the review queue. |
| `POST /api/asks/{ask_id}/choose` | `{"option": 0, "save_meaning": {term, definition, sql_hint?}}` (`save_meaning` is optional) | Picks one reading of a two-meaning question. Approves it, saves it as an example, and returns the review item. |

## Review queue

The caller's own items only (the provider sees all). Another user's item is 404. `open_counts` and `today` count the caller's own asks.

| Method and path | Body | Returns |
|---|---|---|
| `GET /api/review?status=open&level=review&database_id=` | | `{items: [...], open_counts: {"review": 4, "reject": 3}, today: {asked, trusted, review, reject}}`. Send `status=` empty to get all statuses. |
| `GET /api/review/{review_id}` | | `{review_id, source, status, final_sql, final_columns, final_rows, note, created_at, resolved_at, ask: {full ask}}` |
| `POST /api/review/{review_id}/resolve` | see below | The updated item |

Each item in `items` is `{review_id, ask_id, question, database_id, level, reasons, source, status, created_at, resolved_at}`:

- `source` is `auto` or `flagged`.
- `status` is `open`, `approved`, `fixed` or `rejected`.

Resolve body:

```json
{ "action": "fix", "sql": "SELECT ...", "note": "...",
  "save_meaning": { "term": "revenue", "definition": "SUM(payment_value), delivered only" },
  "save_known_number": { "name": "Revenue 2017" } }
```

- `approve`: uses `sql` if it is sent, otherwise the draft SQL.
- `fix`: `sql` is required.
- `reject`: needs no SQL.
- `approve` and `fix` run the SQL again through the verifier. If it does not run, the server returns 400 with `detail.result`.
- After that, the question and SQL are saved as an approved example, plus a known number if one was asked for.
- If the item is already resolved, the server returns 409.

## Saved answers

| Method and path | Body | Returns |
|---|---|---|
| `GET /api/saved` | | `SavedItem[]`, newest first. The caller's own. |
| `POST /api/saved` | `{ask_id, name}` | The new `SavedItem`. 404 if the ask is not the caller's. |
| `DELETE /api/saved/{id}` | | `{ok: true}` |
| `POST /api/saved/{id}/rerun` | | The `SavedItem` after asking the same question again, always fresh (never from the cache). Costs `prices.ask` (402 if the balance is too low). |

```ts
type SavedItem = {
  id: string
  ask_id: string              // the newest run
  name: string
  sql: string                 // "" when the newest run gave no answer (reject)
  level: 'trusted' | 'review' | 'reject'
  last_value: string | null   // answer_text of the newest run
  last_run_at: string
  changed: boolean            // true when the last rerun changed the answer or its level
}
```

## Running SQL

`POST /api/sql/run` with `{"database_id": "...", "sql": "..."}`.

It returns `{status, columns, rows, row_count, truncated, error, elapsed_ms}`.

The SQL goes through the same read-only verifier as every attempt, and anything that writes comes back as `status: "blocked"`.

## Knowledge

| Method and path | Body | Returns |
|---|---|---|
| `GET /api/knowledge?database_id=olist` | | `{meanings: [...], examples: [...], known_numbers: [...]}` |
| `POST /api/knowledge/meanings` | `{database_id, term, definition, sql_hint?}` | The new meaning |
| `DELETE /api/knowledge/{kind}/{id}` | | `{"ok": true}`. `kind` is `meanings`, `examples` or `known`. Admin only (403 for analysts). |
| `POST /api/knowledge/known/{id}/recheck` | | `{ok, changed, saved_value, value_now, result}` |

What each item holds:

- Meaning: `{id, database_id, term, definition, sql_hint, created_at}`
- Example: `{id, database_id, question, sql, columns, rows, from_review_id, created_at}`
- Known number: `{id, database_id, name, question, sql, columns, value, created_at, last_checked_at, last_ok}`

## Databases, models, settings

| Method and path | Returns |
|---|---|
| `GET /api/databases` | `[{id, name, source, available, tables_count}]`. `source` is `preloaded` or `upload`. If `available` is false, the file is not there yet. |
| `POST /api/databases/upload` | Multipart, with the file in the field `file` (CSV, XLSX or SQLite, up to 50 MB). Returns `{id, name, source, available, tables_count, tables, columns}`. 403 when the server has uploads turned off. Old uploads may be deleted automatically (`VERDICT_UPLOAD_TTL_HOURS`). |
| `GET /api/databases/{id}/schema` | `{id, name, tables: [{name, row_count, columns: [{name, type}]}]}` |
| `GET /api/models` | `[{id, label, kind, provider, private, reachable}]`. `kind` is `own` (the user's Qwen model, any version) or `outside` (Gemini and others, used only in the Model Arena). `provider` is how the server reaches it: `openai` (vLLM or Ollama) or `gemini`. Changed 25 Nov: `kind` used to hold what `provider` holds now. |
| `GET /api/settings` | `{database_id, model, second_model, second_model_id}` |
| `PUT /api/settings` | The same fields, all optional. Returns the new settings. Admin only (403 for analysts). |

The preloaded database ids are `olist`, `financial` and `debit_card_specializing`.

The default model ids are `qwen` (vLLM or Ollama) and `gemini`. A setup can list other models, so the frontend should read `/api/models` instead of hard-coding ids.

## Proof pages and health

| Method and path | Returns |
|---|---|
| `GET /api/results` | `results/results.json` as written by the evaluation step. 404 until it exists. |
| `GET /api/arena/models` | The Arena scoreboard: `[{model_id, label, kind, benchmark, n_questions, accuracy, measured_at}]`, from the `arena_models` list in `results/results.json`. `kind` is `own` or `outside`. `accuracy` is 0 to 1, or `null` when not measured yet; the server never fills in a number. `[]` until the evaluation step writes that list. |
| `GET /api/arena` | The list of scripted question keys |
| `GET /api/arena/{key}` | The cached 4-model answers for one question, from `results/arena.json` |
| `GET /api/health` | `{ok, app_db, databases: {id: available}, models: {id: reachable}, attempts, thresholds_placeholder, results_ready}`. `databases` lists only the preloaded ones. |

## Changes from plan section 8

- The levels are now `trusted`, `review` and `reject`, not green, yellow, red, did_you_mean and cannot_answer.
- `reason` became `reasons`, a list of `{code, text}`.
- The inbox is now the review queue, at `/api/review`.
- `/asks/{id}/choose` is now used by the analyst, not a manager. It approves the chosen reading.
- New: `/asks/{id}/flag`, `attempts`, `missing`, `tables_available`, `agreement_level`, `review_id`, and `key` on each check.
- 25 Nov: login, accounts, credits and the provider panel; asks, review items and saved answers belong to their user; `/api/saved`; `/asks/{id}/events`; check status `info`; `kind` on `/api/models` is now `own` or `outside`; `/api/arena/models`. This replaces frontend/ACCOUNTS-API.md.
