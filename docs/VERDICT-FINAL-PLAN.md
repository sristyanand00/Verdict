# Verdict: Final Plan and Build Guide

The AI analyst that knows when not to answer.

Version 1.0, written 18 Nov 2026. Build window: 19 Nov to 8 Dec 2026 (20 days). Buffer: 9 Dec to demo day (about 18 Dec).

This one file holds everything decided so far: what Verdict is, what already exists in the code, every feature and flow, every screen, the backend, the API, how the parts connect, how we prove it works, the 20-day plan, and the demo day script.

---

## Contents

1. [Verdict in one page](#1-verdict-in-one-page)
2. [How we got here: decisions made](#2-how-we-got-here-decisions-made)
3. [What already exists in the code](#3-what-already-exists-in-the-code)
4. [The product flows and features](#4-the-product-flows-and-features)
5. [Features outside the flows](#5-features-outside-the-flows)
6. [Screens: structure of every page](#6-screens-structure-of-every-page)
7. [Backend](#7-backend)
8. [API contract](#8-api-contract)
9. [Connections: how everything talks](#9-connections-how-everything-talks)
10. [Databases we bring](#10-databases-we-bring)
11. [Models: Qwen and Gemini](#11-models-qwen-and-gemini)
12. [Proof: what we measure and how](#12-proof-what-we-measure-and-how)
13. [The 20-day plan](#13-the-20-day-plan)
14. [Demo day script](#14-demo-day-script)
15. [Judge questions and answers](#15-judge-questions-and-answers)
16. [Risks and backups](#16-risks-and-backups)
17. [What we are not building](#17-what-we-are-not-building)
18. [Build guide: how to work through this](#18-build-guide-how-to-work-through-this)

---

## 1. Verdict in one page

### The problem

Companies now let AI answer questions about their data. The AI sometimes gives a wrong answer while sounding completely sure. Nobody can tell which answers are wrong, so an analyst has to re-check every one. Checking takes almost as long as writing the query, so AI has not really reduced the analyst's work.

A second problem: many companies (banks, hospitals, a lot of Indian firms) are not allowed to send their data to a cloud AI at all. They get no AI help.

### What Verdict does

A manager asks a question in plain English. Verdict writes the SQL several times, runs it safely, checks the answers, and decides:

- **Green**: trusted. The manager gets the answer directly, with a receipt showing why.
- **Did you mean?**: the question has two meanings. Verdict asks which one.
- **Can't answer**: the data does not contain this. Verdict says what is missing.
- **Yellow / Red**: not sure, or probably wrong. It goes to the analyst's inbox with a draft.

The analyst only handles the exceptions. Every approval teaches Verdict, so more questions turn green over time.

Verdict can run fully private with our own trained Qwen model, on the company's own machine, with no internet.

### One-line pitch

> "Everyone is building AI analysts. We built the one that knows when it is wrong, and it can run privately on a model we trained ourselves."

### The three layers (how to describe it to recruiters)

- **Product**: an AI teammate for analysts that handles routine questions and routes the rest.
- **Research**: can a verifier reliably tell which text-to-SQL answers are safe to show without a human?
- **Engineering**: a complete, safe, private pipeline around a small open model we trained with execution-based rewards.

---

## 2. How we got here: decisions made

| Decision | Why |
|---|---|
| Not "replace the analyst" | AI agents still score low on multi-step analyst work. The honest claim is: take the repetitive part off the analyst. |
| Not a small Databricks / Snowflake | They are huge platforms. Verdict owns one narrow thing: trust and routing of AI answers. |
| The analyst inbox is the product | The analyst's load drops because they only see yellow/red questions. |
| Qwen is the main engine (private mode) | It gives the training a real purpose: private, offline, cheap. |
| Gemini is optional | Decided on day 6 from Qwen's numbers. Used as cloud mode and as a comparison. |
| Learning loop never skips checks | "Similar question, so green" is unsafe ("this quarter" vs "last quarter"). Approvals improve the prompt; checks still decide the color. |
| No fake confidence numbers | The UI shows tested accuracy with a range, not "97%" per answer. |
| Only real checks on the receipt | Perturbation is a stub, so it is never shown. |
| Olist for the live demo, BIRD for official numbers | Olist is real, messy company data the model has never seen. BIRD is the standard benchmark. |
| Bring 3 to 4 tested databases | Switching databases live shows realness, but only tested ones. |
| 9 core pieces, not 28 | Everything else is "later" or "never". |

Items from the earlier option list and where they ended up:

- **Core**: A1 Workbench (as Ask + Receipt), A5 Review queue (as Analyst Inbox), A9 Trust Report, A10 model comparison (as Model Arena), B2 Ambiguity detector, B3 Confident-wrong checks, B5 Known numbers (light), B8 Private mode, C1/C2 training evaluation, C5 confidence benchmark, C6 unanswerable.
- **Stretch**: C3 shuffled-reward control, C7 hand audit of 100 to 200 BIRD gold queries.
- **Later**: B1 Shadow mode, A4 Postgres, B10 expensive-query blocking, B11 audit pack.
- **Dropped**: A2, A3, A6, A7, A8, B4, B6 (as a separate feature), B7, B9, C4.

---

## 3. What already exists in the code

### Verifier (`verdict/verifier/`), the strongest part

- `safety.py`: read-only connection (`mode=ro`), SQLite authorizer, keyword pre-filter, time deadline.
- `execute.py`: fast in-process run (used in training), max 10,000 rows.
- `pool.py`: runs a query in a separate process that is killed on timeout (used by the product).
- `compare.py`: result comparison. Row order counts only with ORDER BY, 94 equals 94.0, NULL is different from 0 and from empty, duplicates counted.
- `types.py`: results are values, never exceptions. Statuses: ok, blocked, timeout, error, crashed.

### Trust engine (`verdict/engine/`)

- `ingest.py`: upload CSV, Excel (one table per sheet) or SQLite. Cleans column names and keeps a map back to the original names.
- `schema.py`: describes tables and columns to the AI. Names and types only, no rows (privacy).
- `generate.py`: builds the prompt, asks for n attempts, allows `CANNOT_ANSWER`.
- `llm.py`: `SQLWriter` interface, `GeminiWriter` (with disk cache), `FixedWriter` for tests.
- `group.py`: runs every attempt in an isolated process and groups attempts with equal results.
- `trust.py`: decides green / yellow / red / unanswerable from agreement. Empty answers are never green.
- `ask.py`: one function that runs the whole pipeline.
- `thresholds.json`: **placeholder values** (green 0.75, yellow 0.5). Not measured yet.

### Evaluation (`verdict/eval/`)

- `harness.py`: runs the engine on BIRD questions, also runs the gold SQL, saves raw records to JSONL. Can resume.
- `calibration.py`: agreement table, picks thresholds on one half of the questions, reports on the other half.
- `metrics.py`: Wilson 95% confidence range.
- `export.py`, `passk.py`, `taxonomy.py`: **stubs**.

### Training (`verdict/train/`)

- `sft.py`: supervised fine-tuning on BIRD train.
- `grpo.py`, `grpo_utils.py`: GRPO loop (Dr. GRPO style advantage, fp32 weights, fp16 autocast).
- `reward.py`: execution reward, 4 schemes (sparse default, smooth, penalty, normalized).
- `modeling.py`: LoRA setup, load for inference.
- `rollout.py`, `batch.py`, `data_prep.py`, `evaluation.py`, `monitor.py`.
- `control/gsm8k.py`: **stub**.
- **Status**: Qwen2.5-Coder-1.5B is being trained now on the college GPUs. No trained-model results are in `results/` yet.

### Data and audit

- `data/loaders.py`: BIRD dev and train loaders.
- `data/unanswerable.py`: makes unanswerable questions by dropping the tables the gold SQL needs.
- `data/schema.py`: schema with sample rows (for training only).
- `audit/audit.py`, `audit/taxonomy.py`: runs every BIRD gold query. Result: 1,531 of 1,534 run (99.8%). This means "runs", not "is correct".
- `data/perturb.py`, `data/filtering.py`: **stubs**.

### Scripts

`ask.py`, `trace_ask.py`, `check_question.py`, `play_verifier.py`, `review_cases.py`, `run_audit.py`, `run_calibration.py`, `evaluate.py`, `pass_rate.py`, `train_sft.py`, `train_grpo.py`, `train_qwen.py`, `test_training.py`, `watch_changes.py`.

### Tests

About 134 test functions across 24 test files, run in CI (`.github/workflows/ci.yml`).

### Frontend and API

- `verdict/api/main.py`: one line. **Empty.**
- `frontend/src/screens/*.tsx`: comments only (Landing, Console, TrustDial, Audit, Hacking, Dashboard, History). **Empty.** No `package.json` yet.

### Current numbers (honest)

From a small pilot run (34 BIRD questions, Gemini Flash-Lite, 13 Nov 2026):

- When all 8 attempts agreed, the answer was right only **14 of 26 times (54%, range 35% to 71%)**.
- One plain AI answer was right 8 of 17 times on the test half.

The sample is tiny, so these are not results. They do show the key point: **agreement alone is not enough**. That is why Verdict needs extra checks (known numbers, ambiguity split, a second model) and properly measured thresholds.

---

## 4. The product flows and features

```
                         MANAGER
                    "Sales in Pune last month?"
                            |
                            v
   +--------------------------------------------------------+
   |                       VERDICT                          |
   |  schema -> 8 SQL attempts -> safe run -> group results |
   |        -> checks -> decide the color                   |
   +--------------------------------------------------------+
        |            |              |               |
      GREEN     DID YOU MEAN?   CAN'T ANSWER   YELLOW / RED
        |            |              |               |
     Manager    Manager picks   Manager told     ANALYST INBOX
     gets it    A or B          what's missing      |
                                              approve / fix / reject
                                                    |
                                              KNOWLEDGE STORE
                                       (meanings + approved examples
                                            + known numbers)
                                                    |
                                       used on future questions
                                       (checks still decide color)
```

### Flow 1: Set up the data

1. Analyst opens the **Data page**.
2. Picks a preloaded database (Olist, BIRD financial, BIRD debit card, AdventureWorks if ready) or uploads CSV / Excel / SQLite.
3. Verdict scans tables and columns and shows them.
4. Analyst picks the model: Private (Qwen) or Cloud (Gemini, if enabled).
5. Verdict is ready.

Features: database switcher, upload, schema view, model switch, schema selection for big databases (stretch, only for AdventureWorks).

### Flow 2: Manager asks a question (the main flow)

1. Manager types a question on the **Ask page**.
2. Verdict builds the prompt: schema + saved meanings + similar approved examples.
3. The model writes 8 SQL attempts.
4. The verifier runs each one safely in a separate process.
5. Attempts are grouped by result.
6. Checks run (see the list below).
7. Verdict decides the outcome:
   - **Green**: answer shown to the manager, with "View receipt".
   - **Did you mean?**: two big groups with different answers. Manager picks one, and that answer is shown (still marked with its level).
   - **Can't answer**: most attempts said `CANNOT_ANSWER`. Shown with what seems to be missing.
   - **Yellow**: manager sees "An analyst is checking this", and it goes to the inbox.
   - **Red**: same, marked as likely wrong.
8. Every ask is saved (question, attempts, groups, checks, decision).

**The checks (only real ones):**

| Check | What it means | Status |
|---|---|---|
| Safe | Read-only, nothing blocked | exists |
| Ran | The SQL ran without error or timeout | exists |
| Agreement | How many of 8 attempts give the same answer | exists |
| Not empty | Answer is not empty or all NULL | exists |
| No split | Attempts did not split into two big groups | to build |
| Matches known numbers | Does not contradict an approved answer to a near-identical question | to build |
| Second model agrees | Gemini's answer matches (only if Gemini enabled) | to build, optional |

### Flow 3: The analyst works the inbox

1. **Analyst Inbox** lists yellow and red questions, each with its reason. Filters: level, database, date.
2. Analyst opens one on the **Inbox detail page**: question, draft SQL, result, the attempt groups.
3. Analyst can edit the SQL and run it again (same safe verifier).
4. Analyst chooses:
   - **Approve**: the draft is right. Sent to the manager.
   - **Fix**: edited SQL is right. Sent to the manager.
   - **Reject**: cannot be answered. Manager is told why.
5. Optional: **Save a meaning** ("revenue = SUM(price), excluding cancelled orders").
6. Approved and fixed answers are saved as **approved examples** and, if the analyst ticks it, as **known numbers**.

### Flow 4: The learning loop

1. Saved meanings and approved examples appear on the **Knowledge page**.
2. When a new question comes in, Verdict finds the most similar approved examples (text similarity) and adds them, plus matching meanings, to the prompt.
3. The new answer still goes through every check. It is green only if the checks pass.
4. Extra check: if the new question is near-identical to an approved one and the answer differs, it becomes yellow with the reason "differs from an approved answer".
5. Demo moment: first question goes yellow and the analyst fixes it. A similar question afterwards comes back green.

### Flow 5: Private mode

1. Model switch set to Private.
2. Qwen runs on the laptop (Ollama with a GGUF file), with the wifi off.
3. Same checks, same colors.

### Flow 6: Model Arena (demo flow)

1. Open the **Model Arena**.
2. Pick a scripted question (or type one).
3. All 4 machines answer (cached answers for speed and safety).
4. The verifier stamps each one correct or wrong. Verdict shows its color.
5. Below: the scoreboard from the full evaluation.

---

## 5. Features outside the flows

### Proof pages (shown on demo day, not used in daily work)

- **Model Arena**: Qwen base, Qwen SFT, Qwen SFT+GRPO, Gemini, side by side.
- **Trust Dashboard**: green precision with range, coverage, share of questions that needed no human, baselines, unanswerable results, per-database results.

### Engine work (behind the scenes)

- Calibrated thresholds (replace the placeholder `thresholds.json`).
- Full evaluation of all models on 1,534 BIRD dev questions.
- Baselines: single answer, majority vote, refuse everything.
- Hand check of 50 "split" cases (is it really ambiguity?).
- 100 held-out Olist questions written by classmates.
- 20 test questions per demo database.
- FastAPI backend.
- New writer that talks to any OpenAI-compatible server (vLLM on the college GPU, Ollama on the laptop).
- Packaging Qwen for the laptop (merge LoRA, GGUF, Ollama).
- `results.json` export so the proof pages work offline.
- Cached demo answers and a recorded backup video.
- Safety test: hostile queries all blocked, database file hash unchanged after a run.
- Every ask saved as a record (doubles as an audit trail).

### Stretch (only if ahead of schedule)

- Shuffled-reward control run (C3).
- Hand audit of 100 to 200 BIRD gold queries (C7).
- Schema selection for big databases (AdventureWorks).

---

## 6. Screens: structure of every page

You do the visual design. This section fixes what each screen must contain and what data it gets. Design rule for colors: never rely on color alone. Every badge also has a text label (Green / Yellow / Red / Can't answer / Did you mean?).

### Global layout

```
+------------------------------------------------------------------+
| VERDICT   [Ask] [Inbox (7)] [Knowledge] [Data] [Trust] [Arena]   |
|                         DB: Olist v    Model: Private (Qwen) v   |
+------------------------------------------------------------------+
|                                                                  |
|                         page content                             |
|                                                                  |
+------------------------------------------------------------------+
```

- Top bar: logo, page links, inbox count, current database, current model.
- A "role" toggle (Manager / Analyst) is optional. For the demo, simply hide Inbox and Knowledge in Manager view.

### Screen 1: Ask (manager)

```
+------------------------------------------------------------------+
|  Ask your data anything                                          |
|  [ What were sales in Sao Paulo last month?            ] [Ask]   |
|  Try: "orders delivered late in 2018"  "top 5 categories"        |
+------------------------------------------------------------------+
|  [GREEN]  Trusted answer                                         |
|  Sales in Sao Paulo, Aug 2018: R$ 1,284,330                      |
|  +---------------------------+                                   |
|  | total_sales               |   small result table              |
|  | 1284330.12                |                                   |
|  +---------------------------+                                   |
|  Green answers were right 91% of the time in testing (88-94%).   |
|  [View receipt]                                     3.2 s, Qwen  |
+------------------------------------------------------------------+
|  Recent questions (list, each with its badge)                    |
+------------------------------------------------------------------+
```

States of the answer card:

- **Loading**: "Writing 8 attempts... Running safely... Checking..." (step by step, real progress).
- **Green**: answer line, table, tested trust line, receipt button.
- **Did you mean?**: see Screen 3.
- **Can't answer**: see Screen 4.
- **Yellow / Red**: "Not sure enough to answer. Sent to an analyst." Shows the reason. Optional "Show the draft anyway" (marked clearly as unverified).
- **Error**: model or server unavailable.

Data needed: `POST /api/ask` response.

### Screen 2: Receipt

```
+------------------------------------------------------------------+
|  RECEIPT                                              [GREEN]    |
|  Question: What were sales in Sao Paulo last month?              |
+------------------------------------------------------------------+
|  SQL used                                                        |
|  SELECT SUM(p.payment_value) FROM orders o JOIN ...              |
+------------------------------------------------------------------+
|  Result                    (table)                               |
+------------------------------------------------------------------+
|  8 attempts                                                      |
|  (o)(o)(o)(o)(o)(o)(o)  (x)                                      |
|   group A: 7 attempts = 1,284,330      group B: 1 = 1,301,882    |
+------------------------------------------------------------------+
|  Checks                                                          |
|  [pass] Safe: read-only, nothing blocked                         |
|  [pass] Ran: 8 of 8 ran                                          |
|  [pass] Agreement: 7 of 8 give the same answer                   |
|  [pass] Not empty                                                |
|  [pass] No split into two meanings                               |
|  [pass] No conflict with approved answers                        |
|  [ -- ] Second model: off                                        |
+------------------------------------------------------------------+
|  Used knowledge: "sales = payment_value, delivered orders only"  |
|  Model: Qwen 1.5B (trained), private.  Time: 3.2 s               |
|  Tested trust: green right 91% (88-94%) on 1,534 BIRD questions  |
+------------------------------------------------------------------+
```

Data needed: `GET /api/asks/{id}`.

### Screen 3: Did you mean?

```
+------------------------------------------------------------------+
|  [DID YOU MEAN?]  "What was our revenue in 2017?"                |
|  This question can mean two things:                              |
|                                                                  |
|  ( A ) Product price only            R$ 6,155,806   (4 attempts) |
|  ( B ) Price plus freight            R$ 7,142,672   (4 attempts) |
|                                                                  |
|  [Use A]   [Use B]   [Send to analyst]                           |
+------------------------------------------------------------------+
```

- Each option shows a short plain-language description of what that SQL does, the number it gives, and how many attempts chose it.
- Picking one shows that answer. It can be saved as a meaning (analyst only).

### Screen 4: Can't answer

```
+------------------------------------------------------------------+
|  [CAN'T ANSWER]  "What was our advertising ROI in 2018?"         |
|  Your data does not contain advertising spend.                   |
|  Tables available: orders, payments, items, products, ...        |
|  7 of 8 attempts said this cannot be answered.                   |
|  [Ask something else]   [Send to analyst]                        |
+------------------------------------------------------------------+
```

### Screen 5: Analyst Inbox

```
+------------------------------------------------------------------+
|  ANALYST INBOX            Red 3   Yellow 4        Filter: [All v]|
+------------------------------------------------------------------+
|  [RED]    How many customers churned last year?       2 min ago  |
|           Reason: attempts split 3 / 3 / 2, no clear answer      |
|  [YELLOW] Revenue from Rio last quarter?              5 min ago  |
|           Reason: 5 of 8 agree (below green level)               |
|  [YELLOW] Average delivery time for electronics?     11 min ago  |
|           Reason: differs from an approved answer                |
+------------------------------------------------------------------+
|  Today: 18 asked, 11 answered automatically (61%), 7 in inbox    |
+------------------------------------------------------------------+
```

Data needed: `GET /api/inbox`.

### Screen 6: Inbox item detail

```
+------------------------------------------------------------------+
|  < Back   [YELLOW]  Revenue from Rio last quarter?               |
+-------------------------------+----------------------------------+
|  Attempt groups               |  SQL (editable)                  |
|  A: 5 attempts = 812,400      |  SELECT SUM(...) ...             |
|  B: 3 attempts = 901,233      |                                  |
|  (click a group to load SQL)  |  [Run]                           |
|                               |  Result table                    |
|  Why not green:               |                                  |
|  5 of 8 agree, needs 7        |                                  |
+-------------------------------+----------------------------------+
|  [ ] Save as known number                                        |
|  [ ] Save a meaning: [ revenue = ... excluding cancelled ]       |
|  [Approve]   [Approve my fix]   [Reject: reason ...]             |
+------------------------------------------------------------------+
```

Data needed: `GET /api/inbox/{id}`, `POST /api/sql/run`, `POST /api/inbox/{id}/resolve`.

### Screen 7: Knowledge

```
+------------------------------------------------------------------+
|  KNOWLEDGE (what the analyst has taught Verdict)    DB: Olist    |
+------------------------------------------------------------------+
|  Meanings                                                        |
|  revenue   = SUM(payment_value), delivered orders    [edit][del] |
|  late      = delivered after estimated date          [edit][del] |
+------------------------------------------------------------------+
|  Approved examples                                               |
|  "Revenue from Rio last quarter?"  -> SQL, 812,400   approved by |
|                                                      analyst     |
+------------------------------------------------------------------+
|  Known numbers                                                   |
|  Orders in 2017 = 45,101                         [re-check now]  |
+------------------------------------------------------------------+
```

Data needed: `GET/POST/DELETE /api/knowledge/...`.

### Screen 8: Trust Dashboard

```
+------------------------------------------------------------------+
|  TRUST REPORT        Model: [Qwen GRPO v]   Data: [BIRD dev v]   |
+------------------------------------------------------------------+
|  When Verdict says green, it is right   91%  (88-94%)            |
|  Questions answered with no human       52%                      |
|  Confident-wrong answers caught         x of y                   |
+------------------------------------------------------------------+
|  Compared with:                                                  |
|  One plain AI answer      right 55%, always shown                |
|  Majority vote            right 60%, always shown                |
|  Refuse everything        0% coverage                            |
|  Verdict green            right 91%, 52% coverage                |
+------------------------------------------------------------------+
|  Trust slider (from the old TrustDial idea):                     |
|  "Only answer when agreement is at least [ 6 of 8 ]"             |
|  -> answers 52% of questions, 91% of those right                 |
|  (risk-coverage curve chart)                                     |
+------------------------------------------------------------------+
|  Unanswerable: caught 92% (range), wrongly refused 4%            |
|  Per database: Olist held-out, BIRD financial, BIRD debit card   |
+------------------------------------------------------------------+
```

All numbers come from `results.json` (precomputed). Placeholder numbers in this sketch are examples only.

### Screen 9: Data

```
+------------------------------------------------------------------+
|  DATA                                                            |
|  Current: Olist e-commerce (9 tables, 99,441 orders)             |
|  Switch: [Olist] [BIRD financial] [BIRD debit card] [Upload...]  |
+------------------------------------------------------------------+
|  Tables                      | Columns of selected table         |
|  orders          99,441 rows | order_id        TEXT              |
|  order_items    112,650 rows | customer_id     TEXT              |
|  ...                         | order_status    TEXT              |
+------------------------------------------------------------------+
|  Model:  ( ) Cloud - Gemini     (o) Private - Qwen (offline)     |
|  Status: Qwen running locally, 1.5B, last answer 3.2 s           |
+------------------------------------------------------------------+
```

### Screen 10: Model Arena (demo page)

```
+------------------------------------------------------------------+
|  MODEL ARENA      Question: [ pick a scripted question v ] [Go]  |
+---------------+---------------+---------------+------------------+
|  [machine 1]  |  [machine 2]  |  [machine 3]  |   [machine 4]    |
|  small robot  | robot + book  | robot from gym|  giant + cloud   |
|  Qwen Base    | Qwen + SFT    | Qwen SFT+GRPO |  Gemini          |
|  1.5B, local  | 1.5B, local   | 1.5B, local   |  huge, cloud     |
+---------------+---------------+---------------+------------------+
|  SQL ...      |  SQL ...      |  SQL ...      |  SQL ...         |
|  Answer: 412  |  Answer: 388  |  Answer: 388  |  Answer: 388     |
|  [WRONG]      |  [CORRECT]    |  [CORRECT]    |  [CORRECT]       |
|  Verdict: Red |  Verdict: Yel |  Verdict: Grn |  Verdict: Green  |
+---------------+---------------+---------------+------------------+
|  SCOREBOARD (full evaluation)                                    |
|  BIRD dev accuracy (1,534)   X%      Y%      Z%      G%          |
|  Olist held-out (100)        ..      ..      ..      ..          |
|  Runs offline                yes     yes     yes     no          |
|  Cost per 1,000 questions    0       0       0       $..         |
|  Speed per question          ..      ..      ..      ..          |
|  Green right (with Verdict)  ..      ..      ..      ..          |
+------------------------------------------------------------------+
|  "Small model alone loses. Small model + Verdict green = trust." |
+------------------------------------------------------------------+
```

- Machines are your own original artwork.
- Animation: each machine "thinks", prints SQL, then the verifier stamps it.
- Race answers come from cache (`results.json` / demo cache), so it never fails on stage.
- Honesty rules: same questions, same prompt, same scoring for all; show ranges; no "win" claimed for gaps under 3 to 5 points.

### Mapping old frontend stubs to new screens

| Old stub | New screen |
|---|---|
| `Landing.tsx` | Optional intro / start of the demo (can reuse the 3 preset questions idea) |
| `Console.tsx` | Ask + Receipt |
| `TrustDial.tsx` | The slider inside Trust Dashboard |
| `Dashboard.tsx` | Model Arena |
| `History.tsx` | Analyst Inbox + Knowledge |
| `Audit.tsx` | A section of Trust Dashboard (only if the hand audit happens) |
| `Hacking.tsx` | Dropped |

---

## 7. Backend

### Tech

- Python, FastAPI, Uvicorn.
- App state stored in one SQLite file: `data/app.db` (separate from the user databases, which are only opened read-only).
- Models reached through the existing `SQLWriter` interface.

### Folder layout (new parts marked NEW)

```
verdict/
  api/
    main.py                 NEW  FastAPI app, CORS, routers
    routes/
      ask.py                NEW  /api/ask, /api/asks
      inbox.py              NEW  /api/inbox
      knowledge.py          NEW  /api/knowledge
      data.py               NEW  /api/databases, /api/upload, /api/schema
      models.py             NEW  /api/models, /api/settings
      sql.py                NEW  /api/sql/run
      results.py            NEW  /api/results (serves results.json)
    schemas/                NEW  Pydantic request/response models
  engine/
    ask.py                  exists, extended: prompt gets knowledge, returns checks
    llm.py                  exists, add OpenAICompatWriter (vLLM + Ollama)
    group.py                exists
    trust.py                exists, extended: split rule, known-number rule
    ambiguity.py            NEW  detects two big groups, labels each meaning
    knowledge.py            NEW  meanings, approved examples, known numbers, retrieval
    checks.py               NEW  builds the receipt's check list
  store/
    db.py                   NEW  app.db tables and queries
  eval/
    harness.py              exists
    calibration.py          exists
    export.py               NEW (stub today)  writes results.json
    baselines.py            NEW  single / vote / refuse-all numbers
```

### App database (`data/app.db`)

| Table | Columns |
|---|---|
| `databases` | id, name, path, source (preloaded/upload), tables_count, created_at |
| `asks` | id, database_id, question, model, level, answer_rows (json), sql, groups (json), checks (json), reason, latency_ms, created_at |
| `inbox_items` | id, ask_id, status (open/approved/fixed/rejected), final_sql, final_rows (json), note, resolved_at |
| `meanings` | id, database_id, term, definition, sql_hint, created_at |
| `examples` | id, database_id, question, sql, rows (json), from_inbox_id, created_at |
| `known_numbers` | id, database_id, name, question, sql, value (json), last_checked_at, last_ok |
| `settings` | key, value (current db, current model, second model on/off) |

### Decision rules (final version)

Checked in this order:

1. **Can't answer**: more than half the attempts said `CANNOT_ANSWER`.
2. **Did you mean?**: the two largest groups each have at least 3 of 8 attempts, and their answers differ.
3. **Red**: agreement below the yellow threshold, or most attempts failed to run.
4. **Yellow**: any of: agreement between yellow and green threshold; empty answer; conflict with an approved answer; second model disagrees (if on).
5. **Green**: agreement at or above the green threshold and no yellow condition.

Thresholds come from `thresholds.json`, fitted on day 5 from real data (calibration split), and reported on the test split.

### Model writers

- `GeminiWriter`: exists.
- `OpenAICompatWriter` (NEW): one class, takes `base_url` and `model`. It works with:
  - vLLM server on the college GPU (`http://<gpu-pc>:8000/v1`)
  - Ollama on the laptop (`http://localhost:11434/v1`)
- Writers only write SQL. They never decide trust.

### Prompt (extended)

```
system: You write one SQLite query... If the tables cannot answer, reply CANNOT_ANSWER.
schema: <tables and columns>
meanings: revenue = SUM(payment_value) for delivered orders; ...
examples: Q: ... SQL: ...   (top 3 most similar approved examples)
question: <user question>
```

Similarity: TF-IDF over approved questions (no extra model needed, works offline). Upgrade to a small embedding model only if time allows.

---

## 8. API contract

All responses are JSON. Base path `/api`.

### `POST /api/ask`

Request:

```json
{ "question": "What were sales in Sao Paulo last month?", "database_id": "olist", "model": "qwen-grpo" }
```

Response:

```json
{
  "ask_id": "a_102",
  "level": "green",
  "answer_text": "1,284,330.12",
  "columns": ["total_sales"],
  "rows": [[1284330.12]],
  "sql": "SELECT SUM(...) ...",
  "reason": "7 of 8 attempts agree",
  "groups": [
    { "size": 7, "sql": "SELECT ...", "preview": [[1284330.12]] },
    { "size": 1, "sql": "SELECT ...", "preview": [[1301882.0]] }
  ],
  "n_attempts": 8, "n_cannot_answer": 0, "n_failed": 0,
  "checks": [
    { "name": "safe", "status": "pass", "detail": "read-only, nothing blocked" },
    { "name": "agreement", "status": "pass", "detail": "7 of 8" },
    { "name": "second_model", "status": "off", "detail": "" }
  ],
  "options": null,
  "knowledge_used": ["revenue = SUM(payment_value), delivered only"],
  "tested_trust": { "precision": 0.91, "low": 0.88, "high": 0.94, "on": "BIRD dev, 1,534" },
  "model": "qwen-grpo", "latency_ms": 3200
}
```

When `level` is `"did_you_mean"`, `options` is a list:

```json
[ { "label": "Product price only", "sql": "...", "rows": [[6155806]], "size": 4 },
  { "label": "Price plus freight", "sql": "...", "rows": [[7142672]], "size": 4 } ]
```

When `level` is `"cannot_answer"`, `reason` says what seems missing.

### Other endpoints

| Method and path | What it does |
|---|---|
| `GET /api/asks?limit=20` | Recent questions with level |
| `GET /api/asks/{id}` | Full record for the receipt |
| `POST /api/asks/{id}/choose` | Manager picks option A or B (`{"option": 0}`) |
| `GET /api/inbox?status=open&level=red` | Inbox list |
| `GET /api/inbox/{id}` | One item with groups and draft SQL |
| `POST /api/inbox/{id}/resolve` | `{"action": "approve", "sql": "...", "note": "...", "save_meaning": {...}, "save_known_number": true}` (action is approve, fix or reject) |
| `POST /api/sql/run` | `{"database_id": "...", "sql": "..."}` runs through the verifier, returns rows or status |
| `GET /api/knowledge?database_id=olist` | Meanings, examples, known numbers |
| `POST /api/knowledge/meanings` | Add a meaning |
| `DELETE /api/knowledge/{kind}/{id}` | Remove an item |
| `POST /api/knowledge/known/{id}/recheck` | Run a known number again, report if it changed |
| `GET /api/databases` | Preloaded and uploaded databases |
| `POST /api/databases/upload` | Multipart file upload (CSV, XLSX, SQLite) |
| `GET /api/databases/{id}/schema` | Tables, columns, row counts |
| `GET /api/models` | Available models and whether each is reachable |
| `PUT /api/settings` | Current database, model, second-model on/off |
| `GET /api/results` | `results.json` for Trust Dashboard and Model Arena |
| `GET /api/arena/{question_key}` | Cached 4-model answers for one scripted question |
| `GET /api/health` | Server, models and database status |

---

## 9. Connections: how everything talks

```
 +--------------------+        HTTP/JSON         +-------------------------+
 |  FRONTEND          |  --------------------->  |  BACKEND (FastAPI)      |
 |  React + Vite + TS |  <---------------------  |  verdict/api            |
 |  Tailwind          |                          |                         |
 +--------------------+                          |  engine: ask, group,    |
                                                 |  trust, ambiguity,      |
                                                 |  knowledge, checks      |
                                                 +-----+-----------+-------+
                                                       |           |
                                    OpenAI-compatible  |           |  read-only,
                                    HTTP               |           |  separate process
                                                       v           v
              +----------------------+   +----------------+   +--------------------+
              | Qwen on laptop       |   | Qwen on college|   | User databases     |
              | Ollama (GGUF)        |   | GPU (vLLM)     |   | Olist, BIRD, upload|
              | offline demo         |   | evaluation     |   | (SQLite, mode=ro)  |
              +----------------------+   +----------------+   +--------------------+
                                                       |
                                          Gemini API (optional, cloud mode)

              +--------------------+         +-------------------------+
              | data/app.db        |         | results/results.json    |
              | asks, inbox,       |         | precomputed proof for   |
              | knowledge          |         | Trust + Arena pages     |
              +--------------------+         +-------------------------+
```

### Rules

- The frontend never talks to a model or a database directly. Only the backend does.
- User databases are always opened read-only. Every query goes through the verifier.
- Only table and column names go to a cloud model, never rows.
- Proof pages read `results.json`, so they work with no GPU and no internet.
- Demo questions are cached, so the live demo cannot be broken by wifi.

### Where things run

| Setting | Frontend | Backend | Model |
|---|---|---|---|
| Development | `npm run dev` on laptop | `uvicorn` on laptop | vLLM on college GPU, or Ollama |
| Evaluation runs | not needed | scripts on college GPU | vLLM on college GPU |
| Demo day | laptop | laptop | Ollama on laptop (offline) |
| Shareable link (after demo) | Vercel | college GPU PC behind a secure tunnel | vLLM |

Note: vLLM runs on Linux. On Windows gaming PCs, use WSL2, or fall back to Hugging Face generation (slower) or a llama.cpp server.

---

## 10. Databases we bring

| Database | Role | Notes |
|---|---|---|
| **Olist Brazilian E-commerce** (Kaggle) | Main live demo, classmates' held-out test | Real company data, about 100k orders, 9 tables. Natural ambiguity (price vs price plus freight, cancelled orders, split payments). No ad spend, so "ad ROI" is a natural can't-answer. Model has never seen it. |
| **BIRD financial** | Switch-to database, official numbers | Czech bank data. Already in the project. |
| **BIRD debit_card_specializing** | Switch-to database | Fuel-card company. Already in the project. |
| **AdventureWorks** | Only if schema selection works by day 10 | About 70 tables, too big for a 1.5B prompt without table selection. |
| **Live upload** | Realness moment | A judge's CSV, or unseen public CSVs on a USB stick. Tell the room: "On new data it sends more to the analyst. That is the safety working." |

Not bringing: TPC-DS (too big and hard for live use), Spider 2.0 (lives in cloud warehouses, cannot be uploaded; mention as future work).

Olist preparation: load the CSVs into one SQLite file, keep the original column names, add indexes on join keys, check row counts.

---

## 11. Models: Qwen and Gemini

### Qwen (main engine)

- Qwen2.5-Coder-1.5B, three versions: base, SFT, SFT+GRPO (verifier as reward).
- Training is in progress on the college GPUs.
- For the product: the best version is served with vLLM (college GPU) and Ollama (laptop).
- Laptop packaging: merge LoRA into the base weights, convert to GGUF (Q4 or Q5), load in Ollama. Measure speed. If 8 attempts are too slow on CPU, use fewer attempts on the laptop and say so in the receipt, or rely on cached demo answers.

### Gemini (optional)

Decision on **day 6**, after Qwen's numbers:

- Qwen accuracy around 50% or higher, and green coverage at least about 30%: Qwen alone. Gemini appears only in the Arena as a comparison.
- Qwen lower: Gemini becomes "Cloud mode" in the product, Qwen stays as "Private mode".
- Either way, Gemini can be the optional "second model" check.
- Cost: a paid Flash-class run of about 12,000 calls should be cheap. Check current pricing before the run.

---

## 12. Proof: what we measure and how

### A. Model quality (Model Arena)

For Qwen base, SFT, SFT+GRPO and Gemini, on all 1,534 BIRD dev questions, single greedy answer:

- Execution accuracy with 95% range.
- Share of SQL that ran.
- Paired comparison base vs SFT and SFT vs GRPO (same questions, McNemar test).
- Same prompt and scoring for all models.

Rule: do not trust results from 60 or 300 questions. Use the full set.

### B. Verdict quality (Trust Dashboard)

With 8 attempts per question on the best Qwen (and Gemini if used):

- **Green precision**: share of green answers that are right, with range. Target 90%, lower end of range at least 85%.
- **Green coverage**: share of questions that are green. Target at least 30 to 40%.
- **Answered with no human**: green plus correctly handled can't-answer.
- **Confident-wrong**: wrong answers where 8 of 8 agreed. Report how many the extra checks catch.
- **Baselines**: single answer, majority vote, refuse everything. Verdict must beat them on the risk-coverage curve.
- Thresholds fitted on the calibration half, reported on the test half.

### C. Unanswerable

- Recall (caught) target 90%, wrongly refused under 5%.
- Include partial-missing cases (one column or one year missing), not only full tables removed.
- Compare with the refuse-everything baseline (the TrustSQL lesson).

### D. Real-world checks

- 100 Olist questions written by 5 classmates, never seen before the run.
- 20 questions per demo database, green precision for each.
- 50 split cases checked by hand: how many are real ambiguity.

### E. Safety

- Hostile query set: 100% blocked or killed.
- Database file hash unchanged after all runs.

### Honesty rules

- Never show a number without its range.
- Never claim a win for a gap under about 3 to 5 points.
- Say "share of questions that needed no human", not "analyst workload cut", unless real analysts measured it.
- If GRPO adds little over SFT, show that.
- Never show a check that does not run.

---

## 13. The 20-day plan

You design screens in parallel with the backend work. Each block lists what "done" means.

### Days 1 to 3 (19 to 21 Nov): foundations

- Load Olist into SQLite. Write 60 demo questions (easy, ambiguous, impossible, dangerous).
- Message 5 classmates today: each writes 20 Olist questions. You do not read them.
- FastAPI skeleton with `/api/health`, `/api/ask` (wrapping existing `ask.py`), `/api/databases`.
- `OpenAICompatWriter` working against vLLM or another server on the college GPU.
- You: design Ask, Receipt, Inbox, Inbox detail first.
- **Done when**: `curl /api/ask` returns a real answer from Qwen on Olist.

### Days 4 to 6 (22 to 24 Nov): proof numbers

- Greedy evaluation of base, SFT, SFT+GRPO (and Gemini) on 1,534 BIRD dev.
- 8-attempt harness run on the best model.
- Fit thresholds, compute baselines, write the first `results.json`.
- Hand-check 50 split cases.
- Day 6: Gemini decision.
- **Done when**: real numbers replace every placeholder in `thresholds.json` and the dashboard sketch.

### Days 7 to 8 (25 to 26 Nov): checks and learning loop

- `ambiguity.py` (did-you-mean with labels), `checks.py`, `knowledge.py`, app.db tables.
- Inbox endpoints, resolve, meanings, examples, known numbers.
- **Done when**: the demo sequence works through the API: yellow, fix, similar question green.

### Days 9 to 14 (27 Nov to 2 Dec): frontend

- React + Vite + TypeScript + Tailwind, built from your designs.
- Order: Ask and Receipt, then Inbox and detail, then Did-you-mean and Can't-answer states, then Data, Knowledge, Trust, Arena.
- **Done when**: the full 5-question demo runs in the browser.

### Days 15 to 16 (3 to 4 Dec): private mode on the laptop

- Merge, convert to GGUF, Ollama. Measure speed. Cache demo answers.
- **Done when**: the demo runs with the wifi off.

### Days 17 to 18 (5 to 6 Dec): final numbers and slides

- Run the classmates' 100 Olist questions and the per-database checks.
- Final `results.json`. Slides.
- **Done when**: every number on every slide comes from a saved file.

### Days 19 to 20 (7 to 8 Dec): polish

- Rehearse the scripted demo 10 times. Record the backup video.
- **Done when**: a friend can watch the demo without anything going wrong.

### Days 21 to 30 (9 Dec to demo day): buffer

- Fixes, rehearsal, stretch items (hand audit, shuffled-reward control, AdventureWorks).

---

## 14. Demo day script

About 3 minutes. Everything scripted, everything cached.

**0:00 to 0:20, problem**
"Companies use AI to answer data questions. Sometimes it is confidently wrong, and those numbers go into real decisions. So analysts still check everything by hand."

**0:20 to 1:30, product (Olist, manager view)**

1. "What were sales in Sao Paulo last month?" Green, receipt open for 5 seconds.
2. "What was our revenue in 2017?" Did you mean: price only, or price plus freight?
3. "What was our advertising ROI?" Can't answer: no ad spend in the data.
4. A question the model gets wrong. Red, goes to the analyst inbox.

**1:30 to 2:00, analyst and learning loop**

5. Switch to analyst view. Inbox has 1 item. Fix the SQL, save the meaning, approve.
6. Ask a similar question as manager. Green.

**2:00 to 2:20, private mode**

7. Turn the wifi off. Switch to Private. Ask a question. Qwen answers on the laptop.

**2:20 to 2:50, proof (Arena and Trust)**

8. Four machines: base, SFT, GRPO, Gemini. Scoreboard: X, Y, Z, G.
9. "When Verdict says green, it is right N% of the time, tested on 1,534 questions, and on 100 questions our classmates wrote that we never saw."

**2:50 to 3:00, close**
"We did not build another chatbot. We built the part that comes after generation: knowing which AI answers are safe enough that a human does not need to check them."

Optional if asked: switch the database, or upload a judge's CSV.

---

## 15. Judge questions and answers

- **"Isn't this just ChatGPT on SQL?"** ChatGPT gives answers. Verdict checks answers, routes uncertain ones to a human, and its trust level is measured on 1,534 questions.
- **"How do you know it works?"** Calibrated on one half of the questions, tested on the other half, with confidence ranges, plus 100 held-out questions from classmates.
- **"What if all 8 attempts make the same mistake?"** That happens. Our pilot showed 8 of 8 agreement was right only about half the time. That is why there are extra checks: known approved answers, the split detector, and an optional second model. Thresholds are measured, not guessed.
- **"Is your 1.5B model good enough?"** Alone, no. With Verdict, its green answers are trustworthy and the rest go to an analyst. Training raised the green share from A to B.
- **"Doesn't Databricks Genie / Snowflake Cortex Analyst do this?"** They show there is demand for asking data questions in plain language. Verdict focuses on a narrower problem: deciding which answers are safe to show without a human, and running privately on a small model.
- **"Is it safe to run AI-written SQL on company data?"** Read-only connection, SQLite authorizer, separate killable process, time limit, about 134 tests, hostile queries 100% blocked, database file unchanged.
- **"What did GRPO add?"** Show the paired comparison. If it is small, say so: the main gain came from SFT, and that is an honest research result.
- **"What's next?"** Postgres and warehouses, shadow mode next to a real analyst for 2 weeks, and measuring real time saved.

---

## 16. Risks and backups

| Risk | Backup |
|---|---|
| Qwen accuracy too low | Gemini as cloud mode; Qwen stays as private mode with honest numbers |
| GRPO adds nothing over SFT | Report it honestly; story still holds (SFT model + Verdict) |
| Laptop too slow for 8 attempts | Fewer attempts on laptop, cached demo answers, GPU PC on LAN as fallback |
| vLLM will not run on Windows GPU PCs | WSL2, or Hugging Face generation, or llama.cpp server |
| Agreement thresholds give low coverage | Show the trust slider: the trade-off between coverage and accuracy is the honest product |
| Wifi or API fails on stage | Everything cached, offline mode, backup video |
| Frontend takes longer | Build screens in order of the demo; Knowledge and Data pages can be simple |
| Classmates late with questions | Ask on day 1; deadline day 10 |
| Judge uploads a strange file | Test 5 to 10 random CSVs before demo day |

---

## 17. What we are not building

Data pipelines, ETL, streaming, a warehouse, full BI dashboards, charts, a generic chatbot, multi-agent systems, our own vector database, 10 models, login and roles, billing, Kubernetes, many integrations, a semantic layer, recurring reports, the "why did it change" engine, data-request tickets, lineage narratives, the reward-hacking perturbation (C4), and the 25 numbered docs.

---

## 18. Build guide: how to work through this

### Daily routine

1. Morning: open section 13, pick today's block.
2. Build only what that block says.
3. Evening: run the tests (`pytest`), commit, and write one line in `LOG.md`.
4. If something new comes up, write it under "Later" in this file instead of building it.

### Order of building (never change this)

1. Numbers first (they decide what the demo can claim).
2. API second (the frontend needs real data).
3. Screens third, in demo order.
4. Polish last.

### Setup commands (to be confirmed as each part is built)

Backend:

```
pip install -e .
pip install fastapi uvicorn python-multipart
uvicorn verdict.api.main:app --reload --port 8000
```

Frontend (created on day 9):

```
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install -D tailwindcss
npm run dev
```

Model servers:

```
# college GPU (Linux or WSL2)
vllm serve <path-to-merged-qwen> --port 8000

# laptop, offline
ollama create verdict-qwen -f Modelfile
ollama serve
```

### Definition of done for the whole project

- The 3-minute demo runs offline, from a cold start, 10 times in a row.
- Every number on screen and on slides comes from a saved results file, with a range.
- Every check on the receipt is a check that actually runs.
- Tests pass in CI.

### Open decisions (fill in as they are made)

- Day 6: Gemini in product, yes or no.
- Day 10: AdventureWorks, yes or no.
- Day 14: role toggle or two separate views.
- Final demo day date.
