"""Write the "many attempts agreed but the answer was marked wrong" cases to a
file for checking by hand.

    python scripts/review_cases.py                 # agreement >= 6 of 8
    python scripts/review_cases.py --min-agree 8

BIRD's gold answers are not always right, and some questions can be read two
ways. When most attempts agree and still "fail", the cause can be:

    model     the model is wrong (the case the trust engine must catch)
    gold      BIRD's gold SQL is wrong
    ambiguous the question allows both answers

Only "model" cases are real confident errors. Fill in the Label line for each
case; then the share of each label tells how much of the measured error is
real. Output: results/calibration/review.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.config import results_root  # noqa: E402
from verdict.data.loaders import load_bird_dev  # noqa: E402
from verdict.engine.generate import Attempt  # noqa: E402
from verdict.engine.group import run_and_group  # noqa: E402
from verdict.eval.harness import load_records  # noqa: E402
from verdict.verifier.execute import execute_query  # noqa: E402


def show(result, limit: int = 5) -> str:
    if not result.ok:
        return f"{result.status}: {result.error}"
    rows = "\n".join(f"    {r}" for r in result.rows[:limit])
    more = f"\n    ... {len(result.rows) - limit} more rows" if len(result.rows) > limit else ""
    return f"{len(result.rows)} rows, columns {list(result.columns)}\n{rows}{more}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--min-agree", type=int, default=6)
    p.add_argument("--dir", default=str(results_root() / "calibration"))
    args = p.parse_args()

    d = Path(args.dir)
    dev = {t.question_id: t for t in load_bird_dev()}
    cases = [r for r in load_records(d / "answerable.jsonl")
             if r["gold_status"] == "ok" and r["group_sizes"] and r["group_sizes"][0] >= args.min_agree
             and not r["group_correct"][0]]
    cases.sort(key=lambda r: -r["group_sizes"][0])

    out = [f"# Review: agreement >= {args.min_agree}/8 but marked wrong ({len(cases)} cases)\n",
           "Label each case: `model` (model wrong), `gold` (BIRD gold wrong) or `ambiguous`.\n"]
    for i, r in enumerate(cases, 1):
        t = dev[r["question_id"]]
        # Records keep each attempt's SQL but not its group, so regroup to
        # find the SQL of the largest group.
        attempts = [Attempt("sql", sql=s) if s not in ("cannot_answer", "empty") else Attempt(s)
                    for s in r["sqls"]]
        top_sql = run_and_group(attempts, t.db_path, timeout_s=60).top.sqls[0]
        gold = execute_query(t.gold_sql, t.db_path, timeout_s=60, use_first_pass_filter=False)
        cand = execute_query(top_sql, t.db_path, timeout_s=60)
        out += [
            f"\n## {i}. Q{t.question_id} ({t.db_id}, {t.difficulty}): {r['group_sizes'][0]}/{r['n']} agree\n",
            f"**Question:** {t.question}\n",
            f"**Hint:** {t.evidence or '-'}\n",
            f"**Gold SQL:**\n```sql\n{t.gold_sql}\n```\n```\n{show(gold)}\n```\n",
            f"**Model SQL (largest group):**\n```sql\n{top_sql}\n```\n```\n{show(cand)}\n```\n",
            "**Label:** \n",
        ]
    path = d / "review.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"{len(cases)} cases -> {path}")


if __name__ == "__main__":
    main()
