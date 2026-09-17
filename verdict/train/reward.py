"""Verdict -> scalar reward; the reusable public surface.

    __call__(prompts, completions, **kwargs) -> list[float]

Batch in, list of scalars out — matches the TRL/verl expected signature so the
environment drops into an existing training loop unchanged.

Reward scale {1.0 exact match, 0.1 executable-but-wrong, 0.0 otherwise}.
The 0.1 is load-bearing: it creates reward variance inside all-failing groups
(ADR-005, Reconciliation note #3).
"""
