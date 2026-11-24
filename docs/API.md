# Verdict API contract

The frontend builds against this file. Only the Backend chat changes it. If something here does not match what the server returns, the server is wrong. Report it.

- Base path: `/api`. Everything is JSON, except the file upload.
- Errors come back as `{"detail": "..."}` with a normal HTTP status code:
  - 400: bad request
  - 404: not found
  - 409: conflict (for example, the item is already resolved)
  - 422: a field is missing or invalid
  - 503: the model is not reachable
- Live list of routes while the server runs: `http://localhost:8000/docs`.
- Code: `verdict/api/`. Tests: `tests/test_api.py`.

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

## `POST /api/ask`

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
    { "key": "safe", "name": "Safe", "status": "pass", "detail": "Read-only, nothing blocked." }
  ],
  "options": null,
  "missing": null,
  "tables_available": null,
  "knowledge_used": ["revenue = SUM(payment_value), delivered only", "Approved example: \"Revenue in 2017?\""],
  "tested_trust": null,
  "agreement_level": "green",
  "model": "qwen",
  "model_label": "Qwen 1.5B (trained), private",
  "latency_ms": 3200,
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
  - Each `status` is `pass`, `fail` or `off`.
  - `off` means the check did not run, and `detail` says why. Never show `off` as passed.
- `options`: only when the reason is `two_meanings`. Each option is `{label, sql, columns, rows, size, answer_text}`.
- `missing` and `tables_available`: only when the reason is `not_in_data`. `missing` is often `null` because the model usually does not say what is missing.
- `tested_trust`: `{precision, low, high, on}` from `results/results.json`. It is `null` until the Evaluation chat writes that file. Show nothing when it is `null`.
- `agreement_level` is the older agreement-only level (`green`, `yellow`, `red` or `unanswerable`). It is kept for evaluation. The frontend can ignore it.
- `review_id`: anything that is not trusted is added to the review queue, and this is that item's id.

## Asks

| Method and path | Body | Returns |
|---|---|---|
| `GET /api/asks?limit=20&database_id=` | | `[{ask_id, database_id, question, level, answer_text, created_at, flagged}]`, newest first |
| `GET /api/asks/{ask_id}` | | The full `/api/ask` response, plus the current `review_id`, `flagged` and `flag_note` |
| `POST /api/asks/{ask_id}/flag` | `{"note": "..."}` | `{"ok": true, "review_id": "r_..."}`. The analyst says a Trusted answer is wrong, and it goes to the review queue. |
| `POST /api/asks/{ask_id}/choose` | `{"option": 0, "save_meaning": {term, definition, sql_hint?}}` (`save_meaning` is optional) | Picks one reading of a two-meaning question. Approves it, saves it as an example, and returns the review item. |

## Review queue

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

## Running SQL

`POST /api/sql/run` with `{"database_id": "...", "sql": "..."}`.

It returns `{status, columns, rows, row_count, truncated, error, elapsed_ms}`.

The SQL goes through the same read-only verifier as every attempt, and anything that writes comes back as `status: "blocked"`.

## Knowledge

| Method and path | Body | Returns |
|---|---|---|
| `GET /api/knowledge?database_id=olist` | | `{meanings: [...], examples: [...], known_numbers: [...]}` |
| `POST /api/knowledge/meanings` | `{database_id, term, definition, sql_hint?}` | The new meaning |
| `DELETE /api/knowledge/{kind}/{id}` | | `{"ok": true}`. `kind` is `meanings`, `examples` or `known`. |
| `POST /api/knowledge/known/{id}/recheck` | | `{ok, changed, saved_value, value_now, result}` |

What each item holds:

- Meaning: `{id, database_id, term, definition, sql_hint, created_at}`
- Example: `{id, database_id, question, sql, columns, rows, from_review_id, created_at}`
- Known number: `{id, database_id, name, question, sql, columns, value, created_at, last_checked_at, last_ok}`

## Databases, models, settings

| Method and path | Returns |
|---|---|
| `GET /api/databases` | `[{id, name, source, available, tables_count}]`. `source` is `preloaded` or `upload`. If `available` is false, the file is not there yet. |
| `POST /api/databases/upload` | Multipart, with the file in the field `file` (CSV, XLSX or SQLite, up to 50 MB). Returns `{id, name, source, available, tables_count, tables, columns}`. |
| `GET /api/databases/{id}/schema` | `{id, name, tables: [{name, row_count, columns: [{name, type}]}]}` |
| `GET /api/models` | `[{id, label, kind, private, reachable}]` |
| `GET /api/settings` | `{database_id, model, second_model, second_model_id}` |
| `PUT /api/settings` | The same fields, all optional. Returns the new settings. |

The preloaded database ids are `olist`, `financial` and `debit_card_specializing`.

The default model ids are `qwen` (vLLM or Ollama) and `gemini`. A setup can list other models, so the frontend should read `/api/models` instead of hard-coding ids.

## Proof pages and health

| Method and path | Returns |
|---|---|
| `GET /api/results` | `results/results.json` as written by the Evaluation chat. 404 until it exists. |
| `GET /api/arena` | The list of scripted question keys |
| `GET /api/arena/{key}` | The cached 4-model answers for one question, from `results/arena.json` |
| `GET /api/health` | `{ok, app_db, databases: {id: available}, models: {id: reachable}, attempts, thresholds_placeholder, results_ready}` |

## Changes from plan section 8

- The levels are now `trusted`, `review` and `reject`, not green, yellow, red, did_you_mean and cannot_answer.
- `reason` became `reasons`, a list of `{code, text}`.
- The inbox is now the review queue, at `/api/review`.
- `/asks/{id}/choose` is now used by the analyst, not a manager. It approves the chosen reading.
- New: `/asks/{id}/flag`, `attempts`, `missing`, `tables_available`, `agreement_level`, `review_id`, and `key` on each check.
