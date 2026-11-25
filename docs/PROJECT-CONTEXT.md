# Verdict: project context

Read this first. It is the short, current picture of the whole project. Each section points to the file with the details. Written 25 Nov 2026; whoever changes something big updates the matching section here.

Older files describe older versions of the idea. In particular `VERDICT-MASTER-CONTEXT.md` (15 Sept) describes the first framing, "an RL environment for text-to-SQL", which is no longer the product. Use it only as history.

## 1. What Verdict is

**The trust layer for AI-generated analytics.**

An analyst asks a data question in plain English. Verdict's own model writes the SQL 8 times. Each attempt runs read-only in a sandbox. Attempts that return the same rows are grouped. Rules turn the groups into one of three levels, each with reasons and a receipt of the checks that ran:

- **Trusted**: the answer is shown, with the receipt and where the number came from (lineage).
- **Review**: not sure (low agreement, empty answer, clash with an approved answer, two meanings, second model disagrees). It goes to the analyst's review queue with a draft.
- **Reject**: the data cannot answer it, nothing ran, or the attempts disagree too much.

The analyst only checks Review items. Every approval becomes knowledge (an example for the prompt, a known number to check against), so similar questions are more likely to become Trusted later. Knowledge never skips the checks.

The model is the team's own fine-tuned **Qwen2.5-Coder-1.5B**, served by Ollama on a laptop (private, offline) or vLLM on a GPU. Outside models (Gemini and others) are used only in the Model Arena, to compare against it.

**Business model (decided 25 Nov):** Verdict is offered as a service. The provider (role `admin`) gives analysts accounts with credits. Asking a question costs credits; the provider adds or takes back credits and can turn accounts off.

**What we do not claim:** that Trusted answers are right N% of the time (not measured yet), that nothing like this exists, or that agreement equals correctness. Agreement is one model agreeing with itself; see section 6.

## 2. One question, end to end

1. `POST /api/ask` (logged in, enough credits) picks the database and model.
2. `engine/schema.py` describes the tables. `engine/knowledge.py` adds matching meanings and up to 3 similar approved examples (TF-IDF) to the prompt.
3. `engine/generate.py` + `engine/llm.py` ask the model for 8 replies (`VERDICT_ATTEMPTS` changes the number).
4. `engine/group.py` runs every SQL through `verifier/pool.py` (own process, read-only, authorizer, 5 s limit) and groups equal results.
5. `engine/trust.py` gives the agreement level; `engine/ambiguity.py` spots two meanings; `knowledge.find_conflict` compares with approved answers; an optional second model votes. `final_verdict` makes Trusted / Review / Reject.
6. `engine/checks.py` builds the receipt. Only checks that really ran can pass (`info` and `off` exist for the rest). `engine/lineage.py` reads tables, filters and period from the SQL.
7. `api/present.py` makes the JSON; the ask is saved and charged in one transaction; non-Trusted answers go to the review queue.

Code map: `verdict/verifier` (safe execution, the most tested part), `verdict/engine` (the pipeline), `verdict/api` (FastAPI server), `verdict/store` (the app's own SQLite, `data/app.db`), `verdict/train` (SFT and GRPO), `verdict/eval` (calibration), `verdict/data` and `verdict/audit` (BIRD loaders and audit), `frontend/` (React + Vite + Tailwind).

## 3. Who owns what

The project has five parts, each with its own folders. Stay in your own folders; if something elsewhere must change, ask the owner of that part. Every part adds a line to `LOG.md` when it finishes something.

| Part | Owns |
|---|---|
| Frontend | `frontend/` |
| Backend | `verdict/api/`, `verdict/store/`, `verdict/engine/` (not `thresholds.json`), `docs/API.md`, `docs/DEPLOYMENT.md`, `pyproject.toml`, `.gitignore`, `.github/` |
| Training | `verdict/train/`, `scripts/train_*`, `scripts/evaluate.py`, `scripts/pass_rate.py`, `scripts/export_model.py`, model files, training docs |
| Evaluation | `verdict/eval/`, `results/`, `verdict/engine/thresholds.json` |
| Data and demo | `datasets/olist/`, demo questions, demo script and slides |

The user decides. Ask before committing or pushing. No emojis or decorative symbols in code, logs or commit messages. Explanations to the user: plain, short Hinglish.

## 4. What exists and works

**Backend** (tested: 289 tests pass locally; CI on GitHub):
- Every route in `docs/API.md`: ask, asks (history, flag, choose a meaning, events), review queue (approve, fix, reject), knowledge, databases (list, schema, upload), SQL run, models, settings, saved answers, results and arena files, health.
- Accounts: signup, login, logout, bcrypt passwords, hashed tokens, login rate limit. Credits through a ledger; 402 with no credits; server failures not charged; two asks at once cannot go below 0. Provider panel (list accounts, add or take back credits, turn off). Each user sees only their own asks, review items and saved answers; knowledge is shared per database.
- Honest receipt (status `info`; Safe is never a tick; Matches approved is `off` when nothing was compared). Answer lineage.
- Serves `frontend/dist`, so the product can run as one process at `http://localhost:8000`.

**Frontend:** Ask page with the receipt, review queue and detail, history, saved, knowledge, Model Arena, login and account pages, provider (Admin) page. Runs on a browser mock until built with `VITE_USE_MOCK=false`.

**Training:** see `docs/TRAINING_STATUS_FOR_BOOK.md` and `docs/TRAINING_RUNBOOK.md`.

## 5. Real numbers so far

Only numbers with a run behind them. Anything else is "not measured".

- **BIRD dev (1,534 questions), execution accuracy:** Qwen2.5-Coder-1.5B base 24.6%; after SFT v2 43.5%. SFT v2 got 353 questions right that base missed and lost 64 (McNemar p about 1.7e-49).
- **BIRD audit:** 1,531 of 1,534 gold queries run (99.8%). That means "runs", not "is correct".
- **Agreement pilot** (34 BIRD questions, Gemini Flash-Lite): when 8 of 8 attempts agreed, the answer was right 54% of the time. So agreement alone is weak evidence.
- **Not measured yet:** GRPO on 1.5B; trust thresholds (`thresholds.json` holds hand-picked placeholders, and `/api/health` says so); precision of Trusted; how often two meanings are real; speed of 8 attempts on the laptop.

## 6. Known weaknesses (say them before a judge does)

- The trust signal is one model agreeing with itself. Shared mistakes pass every check.
- Nothing checks meaning: a wrong column or a missing filter that all attempts share is not caught.
- The knowledge loop matches words (TF-IDF), so rephrasings can be missed and "last month" answers go stale.
- SQLite only.
- The verifier's keyword pre-filter blocks some harmless SQL (`REPLACE(...)`, strings like `'delete'`); the real protection is the read-only mode and the authorizer.

Full list: `docs/BRUTAL-REVIEW-22NOV.md`.

## 7. What is left

Backend (in order): demo answer cache (`cache_hit`); live Model Arena run (`POST /api/arena/run`, credits for outside models); hardening for a public link (time limit per question, per-user limit, uploads off, no internal error text); clear health check; admin usage stats and a load test (1, 5, 10 users); deployment steps tested.

Needs other parts of the project:
- Ollama on the laptop and the exported model (`verdict-qwen.gguf` + `Modelfile`) from the college PC. Until then no real end-to-end ask has run.
- `datasets/olist/olist.sqlite` and the demo question list (Data and demo).
- Measured thresholds and `results/results.json` with `tested_trust` and `arena_models` (Evaluation).
- Where the backend runs online (a cloud machine, or a PC through Cloudflare Tunnel) and Vercel and Cloudflare accounts.

## 8. How to run it

```
pip install -e ".[app,dev]"
pytest -q
uvicorn verdict.api.main:app --port 8000
```

Settings come from environment variables or `.env` (never committed): model address, attempts, admin account, prices, CORS. All listed in `docs/DEPLOYMENT.md`.

## 9. Where to read more

| For | Read |
|---|---|
| Every route and JSON shape | `docs/API.md` |
| Settings and the three setups (building, laptop offline, public link) | `docs/DEPLOYMENT.md` |
| The full product plan, screens and flows | `docs/VERDICT-FINAL-PLAN.md` (written 18-19 Nov; the accounts and credits model came later) |
| Training: how, status, numbers | `docs/TRAINING_RUNBOOK.md`, `docs/TRAINING_PROTOCOL.md`, `docs/TRAINING_STATUS_FOR_BOOK.md` |
| Honest critique and judge questions | `docs/BRUTAL-REVIEW-22NOV.md` |
| How the verifier works | `verdict/verifier/README.md` |
| What happened, day by day | `LOG.md` |
| The study book | `docs/VERDICT-BOOK.html` |
