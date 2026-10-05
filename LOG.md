# LOG

Build log. One entry per working day: what was built, what broke, how it was fixed, and why each decision was made.

## 2026-09-15 · Day 2
- Repo scaffold created (package layout, pyproject, pytest, docs skeleton).

## 2026-10-01 · Day 8
- Wrote `verifier/types.py`: `ExecutionResult` and `VerificationResult`, both frozen.
- Wrote `execute_query` v1 (`verifier/execute.py`). Not safe yet, no timeout yet (Day 9, Day 10).
- Wrote `tests/fixtures.py` (tiny 3-student DB with one deliberate NULL) and `tests/test_execute.py` (4 tests). `pytest -q`: 5 passed.
- Decided: failure is a returned value, never an exception. One bad query must not kill a long training run.
- Decided: empty result = `ok`. Zero rows can be the right answer ("who failed?" when nobody failed). Treating it as an error would punish the model for being right.
- Decided: `MAX_ROWS = 10,000`. A runaway join could return millions of rows and eat all the RAM. 10,000 is far above any real gold answer.
- Decided: five statuses, not just ok/fail. In Week 3 bad SQL, dangerous SQL, and never-ending SQL must be counted separately.
- Connection is closed in `finally`, so failed queries don't leak file handles.

## 2026-10-01 · Day 9
- Wrote `verifier/safety.py` with three layers: keyword filter, read-only URI, authorizer callback.
- `execute_query` now opens a safe connection and returns `blocked` when SQLite refuses. Added `use_first_pass_filter` flag and a `crashed` catch-all. Timeout left for Day 10.
- Wrote `tests/test_safety.py`: 10 attacks (incl. a DELETE hidden in a CTE). `pytest -q`: 27 passed.
- Decided: the keyword blacklist is layer 1 only, NOT the real control. Writes hide inside CTEs/subqueries, and it blocks innocent SQL (`WHERE name != 'drop'` is blocked; a test shows this).
- Real controls = read-only URI (`mode=ro`) + authorizer (only SELECT/READ/FUNCTION/RECURSIVE allowed). All 10 attacks still blocked with layer 1 switched off.
- Tested that the database is actually unchanged after an attack, not just that we said no.
- Found: SQLite uses two denial messages. 9 attacks say "not authorized", VACUUM says "authorization denied". Missing the second would log an attack as a plain syntax error and corrupt the Week 3 audit counts.

## 2026-10-01 · Setup note
- The plain `python` command on this machine is 3.14, but the project needs 3.11 or 3.12 (see `pyproject.toml`).
  Always use the project venv: `.venv\Scripts\python -m pytest -q`.
- Installed `sqlglot` (a SQL parser) into the venv and added it to `pyproject.toml`. Needed on Day 11.

## 2026-10-01 · Day 10: stop queries that never end
**Why:** the model will sometimes write a query that runs forever. Without a stopper,
one such query freezes the whole training run.

What I built: two stoppers, each covering the other's weak spot.
- **Stopper A, the timer** (`attach_deadline` in `safety.py`). SQLite calls a small function
  every 1,000 steps; once the time limit is passed, it says "stop". Fast, runs inside Python.
  Weak spot: it can't stop something stuck deep inside SQLite's C code.
- **Stopper B, a killable child process** (`pool.py`, `execute_isolated`). The query runs in a
  separate process. If it isn't done in time, we ask it to stop (`terminate`), then force it
  (`kill`). Nothing can refuse a kill. Weak spot: slower, about 0.1 to 0.3 s to start a process.
- `execute_query` now takes `timeout_s` (default 5 s) and returns status `timeout` when the timer fires.

Decisions and why:
- `check_every = 1000`: smaller = Python called too often (slow); larger = a tight loop runs longer before we notice.
- The database is opened **inside** the child process. SQLite connections can't be copied
  between processes; passing one in breaks, sometimes silently.
- `spawn`, not `fork`: the only option on Windows, and it means the same behaviour on the Linux GPU box.
- We wait on the answer queue, not on the process, so we don't wait for the child's shutdown when the answer is already there.
- `finally` always kills a leftover process, so no "zombie" processes pile up.
- **Which one to use where:** training uses `execute_query` (fast). The audit and evaluation use `execute_isolated` (sure).

Result: an infinite query stops in ~1.0 s in-process and ~1.4 s in a child process. 30 tests pass. No leftover python processes.

## 2026-10-01 · Day 11: decide right vs wrong (`compare.py`)
**Why:** this is the most important function. If it says "correct" when the answer is wrong,
the model is trained to give wrong answers.

The rules, and why:
- **Row order only matters if the gold query has `ORDER BY`.** Without `ORDER BY`, SQL promises no order,
  so punishing a different order punishes nothing real.
- **`ORDER BY` is found with a parser (sqlglot), not a text search.** `'order by'` inside a string, or
  an `ORDER BY` in a subquery/CTE, doesn't control the final order. Same lesson as Day 9:
  never text-search a structured language.
- **`94` = `94.0`.** Same number. Numbers are rounded to 4 decimals before comparing.
  Rounding (not "close enough") so values can go into a `Counter`.
- **`NULL` ≠ `''`.** NULL means "unknown", `''` means "known to be empty". Mixing them hides real bugs.
- **Duplicates count, so `Counter`, not `set`.** A set would say `[94, 94, 71]` = `[94, 71]`.
- **Column order doesn't matter.** `SELECT name, score` and `SELECT score, name` answer the same question.
- **Trailing spaces are ignored** (`"Priya "` = `"Priya"`): that's messy data, not a SQL mistake.
- `True` is checked before numbers, because in Python `True` counts as the integer 1.
- Values get a tag (`("null",)`, `("num", 94.0)`, `("str", "Priya")`) so NULL can never accidentally equal "null", 0 or False.
- If the **gold** query fails, the verdict is `invalid` with reason `GOLD FAILED`, not blamed on the model.
  Counting these is the Week 3 benchmark audit.

## 2026-10-01 · Day 12: try to break my own verifier
**Why:** "I built a verifier" means little. "I attacked it, and here's what broke" shows real skill.

- Wrote the adversarial suite in `tests/test_compare.py`: 30 comparison cases (formatting, NULL/empty,
  duplicates, shape and types, ORDER BY edge cases, gold failures), plus 6 ORDER BY detection cases.
  Together with Day 9's 10 attacks and Day 10's runaway queries: 69 tests, all passing.
- The guide's cases all passed first time, so I added my own cases. Those found real bugs:

**REAL BUGS FOUND:**
1. **(Day 9) SQLite has two refusal messages.** 9 attacks say "not authorized", VACUUM says
   "authorization denied". Missing the second would count an attack as a plain syntax error.
2. **Values swapped between rows were judged correct.** To ignore column order, the first version
   sorted the values inside each row separately. So `[(1,2), (2,1)]` turned into `[(1,2), (1,2)]`
   and matched a gold answer that is clearly different.
   Fix: try each possible column order, applied **the same way to every row**.
3. **That fix made wrong answers very slow.** A wrong 6-column, 10,000-row answer took **22 seconds**
   (it tried all 720 column orders). Wrong answers are the most common case in training, so this
   would have crushed training speed. Fix: a quick pre-check. A column can only match a column
   that holds exactly the same values. Now **0.1 seconds**.

**Known gaps, written as tests on purpose (so they're visible, not hidden):**
- `SELECT 'Priya', 94` (just printing the answer) is marked correct. That's reward hacking.
  Fix is in **Week 6**: re-run the query on a changed copy of the database.
- Rounding edge: 0.00005 vs 0.00004 disagree after rounding. Accepted.
- With more than 6 columns, other column orders are not tried (too slow). Accepted, BIRD answers are rarely that wide.

## 2026-10-01 · Day 13: turn the verdict into a training score (`train/reward.py`)
**Why:** in Week 4 the training library (TRL/GRPO) hands over a batch of model answers and expects
one number for each. Building that shape now means Week 4 just plugs in.

The scale, and why:
- **1.0** = ran and the answer matched gold.
- **0.1** = ran but the answer was wrong.
- **0.0** = didn't run (error, blocked, timeout).
- **The 0.1 is the important part.** At the start almost every answer is wrong. If everything scored 0,
  GRPO would have nothing to compare, the model would learn nothing, and the loss curve would still
  look normal. 0.1 vs 0.0 gives a difference from day one.

Decisions and why:
- `extract_sql` takes the **last** ```sql block: models often try something, then give the final answer at the end.
- A **module-level class**, not a nested function: nested functions can't be pickled, and training sends
  this object to other processes. A test checks it pickles.
- **Threads, not processes**, for scoring a batch: SQLite lets threads run truly in parallel, and threads are much cheaper.
- The gold query skips the keyword doormat: gold is trusted, and our own filter must not refuse it.

Result: the reward test returns exactly `[1.0, 0.1, 0.0, 0.0]` for right / wrong / broken / attack. 74 tests pass.

## 2026-10-01 · Day 14: write-up
- Wrote `verdict/verifier/README.md`: what each file does, plus plain answers to the 7 "why" questions
  (blacklist vs real controls, row vs column order, why open the DB inside the child, Counter vs set,
  the 0.1 reward, known gaps, and the bugs the tests found).
- Final state: **74 tests passing**, no leftover processes, ₹0 spent, no GPU used.
- Week 2 verifier is done. Next is Week 3: run it on BIRD and audit the gold answers.

## 2026-10-01 · Prepared the verifier for GitHub
- Rewrote code comments and docstrings in a neutral technical style. Removed course-plan references
  ("Day 12", "Week 6") from the code, since a reader of the repo doesn't have the plan. The plan lives in this log.
- Rewrote `verdict/verifier/README.md` as reference documentation: modules, usage, design rules, defects found, known limits.
  Checked the usage example on a real BIRD database (`california_schools`, 17,686 rows, verdict `correct`).
- Updated the project README status table: the verifier and reward are done; the rest is still stubs.
- No logic changed. `pytest -q`: 74 passed.

## 2026-10-03 · Tested the verifier by hand
- Added `scripts/play_verifier.py`: rebuilds the test database at `scratch/tiny/tiny.sqlite`, prints both
  tables, then lets me type SQL and see status, rows, verdict and score. `--demo` runs six fixed examples.
- Tested the verifier by hand on the mock database with it, predicting each result on paper first.
- Example: a typo (`ORDER BY name DES`) came back as status `error`, verdict `invalid`, score 0.0.
  The message `near "DES": syntax error` is written by SQLite itself; `execute.py` only reads the message
  and sorts it into a status (interrupted = timeout, not authorized / readonly = blocked, anything else = error).
- Understood: the verifier needs a gold query to say "correct". With a real user there is no gold, which is
  why the project later estimates confidence from several attempts agreeing.

## 2026-10-03 · First look at real BIRD gold queries
- Ran 60 random BIRD dev gold queries through `execute_query` (gold mode, 30 s limit): all 60 `ok`, none empty.
- 4 of the 60 took 2 to 4 seconds (slowest: question 530, 3.9 s). The default limit is 5 s.
- Consequence for Day 15: gold queries need a bigger time limit, or slow but valid gold answers will be
  wrongly counted as GOLD FAILED. Gold results should be run once and cached, not re-run in every training step.

## 2026-10-03 · BIRD loader (left over from Day 6)
**Why:** every later step (caching gold results, the audit, training, evaluation) reads BIRD. One loader
means they all read it the same way, with the same paths and the same checks.

- `verdict/data/loaders.py`: `load_bird_dev()` returns a list of `BirdTask`
  (question_id, db_id, question, evidence, gold_sql, difficulty, db_path).
- Paths come from `verdict/config.py` (`dev_json()`, `db_path()`), never hard-coded, so the data can move
  with `VERDICT_DATA_ROOT`.
- `data_root` can be changed, so the same questions can later point at perturbed database copies (Week 6).
- Decided: the loader **raises** on bad data, unlike the verifier. A missing field, unknown difficulty,
  duplicate id or missing database file should stop a run at the start, not show up later as thousands of
  failed queries. All missing databases are reported in one message.
- Text is trimmed of surrounding whitespace. 148 questions have an empty `evidence` hint; kept as `""`.
- `tests/test_loaders.py`: 6 tests on a fake `dev.json` (run in CI, no BIRD needed) + 1 test on the real
  data that checks 1,534 questions, 11 databases, 925 / 464 / 145 by difficulty (skipped if BIRD is absent).
- `pytest -q`: 81 passed.
