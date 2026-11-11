#!/usr/bin/env python3
"""Run the BIRD gold-query audit, then print a breakdown of the failures.

    python scripts/run_audit.py

Takes roughly 10-30 minutes: each of the 1,534 queries runs in its own process.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict import config  # noqa: E402
from verdict.audit.audit import run_audit  # noqa: E402
from verdict.audit.taxonomy import summarize_errors  # noqa: E402
from verdict.data.loaders import DIFFICULTIES  # noqa: E402

SHOW_PROBLEMS = 10


def analyze_results(audit_json: Path) -> None:
    with open(audit_json, encoding="utf-8") as f:
        results = json.load(f)
    total = len(results)

    print("\nERROR TAXONOMY")
    for category, n in summarize_errors(results).items():
        pct = 100 * n / total
        print(f"  {category:<18} {n:>5}  ({pct:5.1f}%)  {'#' * int(pct / 2)}")

    print("\nBY DIFFICULTY")
    for diff in DIFFICULTIES:
        rows = [r for r in results if r["difficulty"] == diff]
        if not rows:
            continue
        counts = Counter(r["status"] for r in rows)
        detail = ", ".join(f"{s} {n}" for s, n in sorted(counts.items()) if s != "ok")
        print(f"  {diff:<12} {counts['ok']}/{len(rows)} ok" + (f"  ({detail})" if detail else ""))

    problems = [r for r in results if r["status"] != "ok"]
    print(f"\nPROBLEM QUERIES ({len(problems)}/{total}; first {SHOW_PROBLEMS} shown)")
    for r in problems[:SHOW_PROBLEMS]:
        print(f"  Q{r['question_id']} [{r['db_id']}, {r['difficulty']}] {r['status']}: {(r['error_msg'] or '')[:100]}")


if __name__ == "__main__":
    audit_json = config.results_root() / "audit.json"
    run_audit(output_json=audit_json)
    analyze_results(audit_json)
