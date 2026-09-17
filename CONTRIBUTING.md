# Contributing

Solo project (OJT Semester 4), but the workflow is kept professional because the
engineering practice is itself assessed.

## Branching

- `main` — always demo-ready
- `feature/*` — development
- `experiment/*` — training runs and configs; never merged into `main` unless the
  config becomes canonical

## Quality gates

A pull request must pass, in order: lint + type check, unit tests (verifier semantics,
advantage computation), the **adversarial SQL suite (blocking)**, integration + API tests,
frontend build + component tests, secret + dependency scan, and artifact schema validation.

## Rules

- `datasets/` and `models/` never enter git history.
- Every experiment records run id, model, dataset + split, prompt version, config, seed,
  training params, reward config, checkpoint and results.
- Negative and surprising results are reported alongside positive ones.
