# Repository structure — and why it looks like this

`VERDICT-MASTER-CONTEXT.md` contains **three** repository layouts that do not agree:

| # | Where | What it is |
|---|---|---|
| A | Part I, §I.36 "Suggested Repository Structure" | portal-facing, written earliest |
| B | Part II, "GitHub Repository Structure" + "Repository Modules" (LLD) | the detailed design |
| C | Part V, Day 2 Block 2 "Repo scaffold" | the thing actually being built |

The master file's own Reconciliation note #2 sets the precedent: **Part I is the
portal-facing document; Parts III–V are what gets executed.** The same rule is applied
below wherever the three disagree.

## Conflicts and resolutions

| Conflict | A (Part I §I.36) | B (LLD / GitHub) | C (Day 2) | **Resolved to** |
|---|---|---|---|---|
| Package sub-modules | `rewards/`, `perturbations/`, `training/`, `evaluation/` | `train/`, `eval/` | `train/`, `eval/` | **B + C** — short names, 2 sources to 1, and it is what Day 2 builds |
| Artifact directory | `artifacts/` | `results/` | `results/` | **`results/`** — also what the Day 2 `.gitignore` references (`results/*.json`) |
| Frontend | `apps/web/` | `frontend/` | — | **`frontend/`** |
| API service | `apps/api/` | `verdict/api/` | — | **`verdict/api/`** — the API is part of the package, not a sibling app |
| Benchmark audit | `benchmark_audit/` | *(absent)* | *(absent)* | **`verdict/audit/`** — Deliverable 2 needs a home; renamed to match the short-name convention the rest of the package uses. Rename to `benchmark_audit/` if you prefer §I.36 verbatim. |
| Repo root | `verdict/` as the repo | same | the `ojt sem4` folder itself | **this folder is the repo root**, per Day 2 (`cd "…\ojt sem4"` then `git init`) |
| `tests/` location | root | LLD nests it at `verdict/tests/`; GitHub structure puts it at root | root | **root** — 2 sources to 1, and Day 2 builds it there |
| BIRD dev location | — | — | `datasets/` flat | **`datasets/dev.json` + `datasets/dev_databases/`** — see below |

## Two `taxonomy.py` files — not a mistake

- `verdict/audit/taxonomy.py` — **annotation-error** taxonomy (which BIRD gold queries are wrong, and how)
- `verdict/eval/taxonomy.py` — **failure** categorisation (how the model's queries fail)

Different artifacts, different deliverables. Named per §I.36 and the LLD respectively.

## BIRD dev set — unzips flat into `datasets/`

No `bird/` wrapper. Three executable references fix this:

- Day 1 instruction: "Make a folder `datasets/` … and unzip BIRD into it"
- Day 3 snippet: `sqlite3.connect("datasets/dev_databases/<db>/<db>.sqlite")`
- Day 7 test: `load_bird_dev(Path("datasets/dev.json"))`

The `bird/` parent shown at master-file line 6810 describes **what the BIRD zip contains**,
not a project path. A `datasets/bird/` directory was created and then removed for this reason.
See `datasets/README.md`.

## Deliberate additions
- `models/` added to `.gitignore` — checkpoints must never enter git history, the same
  reason the master file gives for `datasets/`
- `STRUCTURE.md`, `LOG.md`, `docs/` stubs, `.github/workflows/ci.yml` — scaffolding the
  plan calls for but does not spell out byte-for-byte

## Not yet done

`git init` has **not** been run — the scaffold is on disk only. Day 2 Block 2 continues:

```powershell
git init
uv venv --python 3.11 .venv
.\.venv\Scripts\Activate.ps1
uv pip install pytest
uv pip install -e .
pytest -q
git add -A
git commit -m "Scaffold: package layout, pyproject, pytest"
```
