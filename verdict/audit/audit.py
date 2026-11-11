"""Benchmark audit: run every BIRD gold query and record whether it executes.

A gold query that errors or times out is a benchmark defect. Training on it
would reward the model for disagreeing with a broken answer, so these cases
are counted and reported rather than blamed on the model.
"""

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from verdict import config
from verdict.data.loaders import load_bird_dev
from verdict.verifier.pool import execute_isolated
from verdict.verifier.types import Status


@dataclass(frozen=True)
class AuditResult:
    question_id: int
    db_id: str
    difficulty: str
    status: Status
    error_msg: str | None = None
    elapsed_ms: float = 0.0


def run_audit(
    dev_json: Path | None = None,
    output_json: Path | None = None,
    timeout_s: float = 5.0,
) -> dict[str, int]:
    """Run every gold query in a killable child process; save results and return status counts.

    Results go to ``output_json`` (default ``<results>/audit.json``).
    """
    output_json = output_json or config.results_root() / "audit.json"
    tasks = load_bird_dev(dev_json)
    print(f"Running {len(tasks)} gold queries (timeout {timeout_s}s each)...")

    results = []
    start = time.time()
    for i, task in enumerate(tasks, 1):
        r = execute_isolated(task.gold_sql, task.db_path, timeout_s=timeout_s)
        results.append(
            AuditResult(task.question_id, task.db_id, task.difficulty, r.status, r.error, r.elapsed_ms)
        )
        if i % 100 == 0:
            elapsed = time.time() - start
            print(f"  {i}/{len(tasks)}  ({elapsed:.0f}s elapsed, ~{elapsed / i * (len(tasks) - i):.0f}s left)")

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    counts = Counter(r.status for r in results)
    total = len(results)
    print(f"\nAudit finished in {time.time() - start:.1f}s; results saved to {output_json}")
    for status in ("ok", "error", "timeout", "blocked", "crashed"):
        n = counts.get(status, 0)
        print(f"  {status:<8} {n:>5}  ({100 * n / max(total, 1):5.1f}%)")
    return {s: counts.get(s, 0) for s in ("ok", "error", "timeout", "blocked", "crashed")}


if __name__ == "__main__":
    run_audit()
