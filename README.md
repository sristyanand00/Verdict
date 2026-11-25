# Verdict

**A verifiable reinforcement-learning environment for text-to-SQL, and a SQL assistant that
knows when it is wrong.**

> **Status: in development.** The execution verifier, reward function and GRPO training loop
> are implemented and tested. Training runs on the college GPU PC; see
> [docs/TRAINING_RUNBOOK.md](docs/TRAINING_RUNBOOK.md) and
> [docs/TRAINING_STATUS_FOR_BOOK.md](docs/TRAINING_STATUS_FOR_BOOK.md).
> See [Project status](#project-status).

## Problem

Natural-language-to-SQL is shipped by every major data platform and trusted by almost
nobody. The problem is less accuracy than visibility: a wrong answer does not look wrong. A query
that misses a join or filters the wrong literal returns a plausible number with no error and
no warning. One silent failure is enough to end an organisation's trust in the tool.

## Approach

Verdict turns SQL correctness into an objective, automatic signal (execute the query,
compare the rows) and uses it in three ways:

1. to train a small open-weight model with reinforcement learning,
2. to audit whether the benchmark's own gold answers are correct, and
3. to estimate confidence so the assistant can **abstain instead of guessing**.

## Planned capabilities

These are the deliverables the project is being built toward. The first two are complete.

- Sandboxed, read-only, timeout-enforced SQL execution (done)
- Deterministic result-set normalisation and comparison (done)
- Multi-database perturbation verification (catches memorised answers)
- GRPO training pipeline with a control-domain gate
- Benchmark ground-truth audit with a hand-built error taxonomy
- Unanswerable-question benchmark
- Confidence estimation and a risk-coverage operating curve
- Side-by-side base vs trained comparison with executed results
- Reusable reward-function package

## Intended architecture

React + Tailwind → FastAPI → verification sandbox (SQLite, isolated processes) →
SFT and GRPO trainers (hand-written loops on transformers and PEFT) → experiment store → `results.json` artifact.

**Tech stack:** Python, FastAPI, React, Tailwind CSS, PyTorch, transformers, PEFT, Ollama or vLLM for serving, Pandas, SQLite.

## Project status

| Area | State |
|---|---|
| Repo scaffold, packaging (`pyproject.toml`), pytest | Done |
| Path configuration (`verdict/config.py`) | Done |
| GitHub Actions CI (unit-test gate) | Done |
| Execution verifier (`verdict/verifier`): safety, timeouts, comparison | Done, 74 tests ([details](verdict/verifier/README.md)) |
| Reward function (`verdict/train/reward.py`) | Done |
| GRPO training loop (`verdict/train/grpo.py`, `scripts/train_grpo.py`) | Done, tested on a tiny model; first GPU runs in progress |
| `eval`, `audit`, `data`, `api` | In progress |
| `frontend/` screens | Stubs |
| Experimental results | Not started |

The build log is in [`LOG.md`](LOG.md). The product plan is in
[`docs/VERDICT-FINAL-PLAN.md`](docs/VERDICT-FINAL-PLAN.md).

## Repository layout

```
verdict/          Python package
  config.py         single source of truth for data + results paths
  verifier/         sandboxed execution, comparison, safety
  train/            GRPO rollout, reward, control domain
  eval/             metrics, calibration, pass@k, export
  audit/            benchmark ground-truth audit + error taxonomy
  data/             BIRD loaders, filtering, perturbation, schema
  api/              FastAPI service
frontend/         React + Tailwind client
docs/             design documents (01 to 25)
scripts/          data fetch + utility scripts
configs/          experiment configuration
tests/            pytest suite
results/          run artifacts (gitignored)
datasets/         BIRD corpora (gitignored, never committed)
```

## Getting started

Requires Python 3.11 or 3.12.

```bash
git clone https://github.com/sristyanand00/verdict.git
cd verdict

python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -e .
pip install pytest
pytest -q
```

### Configuration

Copy `.env.example` to `.env` and adjust. Nothing in it is secret; secrets are never
committed.

| Variable | Meaning | Default |
|---|---|---|
| `VERDICT_DATA_ROOT` | Where the BIRD corpora live | `<repo>/datasets` |
| `VERDICT_RESULTS_ROOT` | Where run artifacts are written | `<repo>/results` |

The benchmark corpora are large and are **not** part of the repository. Fetch them with
[`scripts/fetch_bird.ps1`](scripts/fetch_bird.ps1), then verify the paths resolve:

```bash
python -m verdict.config
```

## Running

Once built, the demonstration application is intended to run from a cold start with **no GPU
and no network**, serving the pre-computed results artifact. Live generation will be optional
and require a GPU. Reproducing training will require a single GPU and a configuration file.

## Results

Training results so far are in [`docs/TRAINING_STATUS_FOR_BOOK.md`](docs/TRAINING_STATUS_FOR_BOOK.md),
with every number traceable to a run. **Negative and surprising results are reported alongside
positive ones.**

## Licence

See [`LICENSE`](LICENSE).

## Important disclaimer

Verdict is a student research and decision-support prototype. It generates read-only queries
for human inspection. It must not be connected to a production database or used to produce
figures for real decisions without independent validation, governance and human oversight.
