# Verifier

Execution-based verification for text-to-SQL. Given a candidate query, a gold
query and a SQLite database, the verifier runs both queries safely and returns
`correct`, `wrong` or `invalid`, together with the reason. The same component
provides the training reward, the benchmark audit and the evaluation metric.

## Modules

| File | Responsibility |
|---|---|
| `types.py` | `ExecutionResult` and `VerificationResult`. Frozen dataclasses; failures are values, not exceptions. |
| `safety.py` | Read-only connection, authorizer callback, keyword pre-filter, in-process deadline. |
| `execute.py` | `execute_query`: run one query in-process. Fast path, used in training. |
| `pool.py` | `execute_isolated`: run one query in a killable child process. Used for audit and evaluation. |
| `compare.py` | `compare_results`: decide whether two result sets are equivalent. |
| `../train/reward.py` | `SQLRewardFunction`: batch reward in the TRL/verl signature. |

## Usage

```python
from verdict.verifier.execute import execute_query
from verdict.verifier.compare import compare_results

db = "datasets/dev_databases/california_schools/california_schools.sqlite"
gold_sql = "SELECT COUNT(*) FROM schools"

cand = execute_query("SELECT COUNT(*) FROM schools", db)
gold = execute_query(gold_sql, db, use_first_pass_filter=False)
result = compare_results(cand, gold, gold_sql)

result.verdict  # "correct" | "wrong" | "invalid"
result.reason   # e.g. "unordered compare (no ORDER BY)"
```

## Design

### Execution status

Every query produces one of five statuses: `ok`, `blocked`, `timeout`, `error`
or `crashed`. They are kept distinct because invalid SQL, unsafe SQL and
non-terminating SQL are separate findings in the audit. An empty result is `ok`:
zero rows can be the correct answer.

### Safety

Three independent layers:

1. **Keyword pre-filter.** Rejects statements containing write keywords before a
   connection is opened. It is a cost optimisation only: writes can be hidden
   inside CTEs (`WITH t AS (SELECT 1) DELETE FROM students`), and it rejects
   valid queries such as `WHERE name != 'drop'`.
2. **Read-only URI** (`mode=ro`). The SQLite driver refuses to open a writable
   handle, whatever the statement contains.
3. **Authorizer callback.** SQLite consults it for every operation while
   compiling the statement. Only `SELECT`, `READ`, `FUNCTION` and `RECURSIVE`
   are allowed; `ATTACH`, `PRAGMA`, `VACUUM` and all writes are denied.

Layers 2 and 3 are the security controls. The test suite disables layer 1 and
confirms that every attack is still blocked and that the database is unchanged.

### Termination

- **In-process deadline.** A SQLite progress handler aborts the statement once
  the time limit passes. Cheap, but it cannot interrupt a hang inside C code.
- **Child process.** `execute_isolated` runs the query in a separate process and
  escalates from `terminate()` to `kill()` on timeout. The connection is opened
  inside the child because SQLite connections cannot be shared across processes.
  The `spawn` start method is used on every platform.

Training uses the in-process path for throughput. The audit and evaluation use
the child-process path.

### Result comparison

| Question | Rule | Rationale |
|---|---|---|
| Row order | Significant only if the outermost gold query has `ORDER BY` | SQL guarantees no order otherwise. `ORDER BY` is detected with a parser (sqlglot), not text search. |
| Column order | Not significant | `SELECT a, b` and `SELECT b, a` answer the same question. A reordering must apply to every row. |
| `94` vs `94.0` | Equal | Numbers are rounded to 4 decimal places. |
| `NULL` vs `''` or `0` | Not equal | NULL means unknown; it is not an empty or zero value. |
| Duplicate rows | Counted | Multiset (`Counter`) comparison. A set would treat `[94, 94, 71]` as `[94, 71]`. |
| Surrounding whitespace | Ignored | Treated as data-entry noise rather than a query error. |

A failing gold query yields `invalid` with reason `GOLD FAILED`, so benchmark
defects are not counted against the model.

### Reward

| Outcome | Reward |
|---|---|
| Query ran and the result matches gold | 1.0 |
| Query ran, result does not match | 0.1 |
| Query did not run (error, blocked, timeout) | 0.0 |

The 0.1 tier gives reward variance to groups in which every completion is wrong.
With a binary reward such groups produce a zero group-relative advantage in
GRPO and therefore no gradient, which is the common case early in training.
The scale follows Arctic-Text2SQL-R1 (arXiv:2505.20315).

## Defects found by the adversarial tests

1. **Two authorizer denial messages.** SQLite reports most denials as
   `not authorized` but `VACUUM` as `authorization denied`. Matching only the
   first recorded `VACUUM` as an ordinary SQL error rather than a blocked attack.
2. **Per-row sorting accepted wrong answers.** An early version ignored column
   order by sorting the values inside each row independently, which judged
   `[(1, 2), (2, 1)]` equal to `[(1, 2), (1, 2)]`. Comparison now searches for a
   single column permutation applied to all rows.
3. **Permutation search was slow on wrong answers.** Trying all 720 orders for a
   wrong 6-column, 10,000-row result took about 22 s. Pruning by per-column value
   multisets reduced this to about 0.1 s.

## Known limitations

- **Constant answers pass.** `SELECT 'Priya', 94` returns the expected rows
  without reading any table and is judged correct. This is a reward-hacking
  path. The planned fix is to require the query to also be correct on perturbed
  copies of the database. A test asserts the current behaviour.
- **Rounding boundaries.** Values on either side of a rounding boundary
  (`0.00005` vs `0.00004`) compare as different.
- **Wide results.** Above 6 columns, alternative column orders are not tried.
- **Row cap.** Only the first 10,000 rows are read.

## Tests

```bash
pytest -q
```

| File | Covers |
|---|---|
| `tests/test_execute.py` | Execution, empty results, NULLs, runaway queries in-process and in a child process |
| `tests/test_safety.py` | 10 hostile statements, with and without the keyword filter; database integrity after an attack |
| `tests/test_compare.py` | 30 comparison cases, gold and candidate failures, `ORDER BY` detection |
| `tests/test_reward.py` | SQL extraction, the reward scale, reward variance, pickling |
