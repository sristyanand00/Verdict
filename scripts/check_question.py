"""Check BIRD questions one at a time: ask the trust engine, then open the
answer key and see whether it was right.

    python scripts/check_question.py 733
    python scripts/check_question.py 733 861 82 995 1194
    python scripts/check_question.py --random 5

For each question it prints five steps:
  1. the BIRD question (and its hint)
  2. the 8 SQL attempts from the AI
  3. the groups and the trust level, exactly as the product decides it
  4. BIRD's answer key: the gold SQL and its result
  5. right or wrong
and, for several questions, a small register at the end.

Gemini replies are cached in scratch/llm_cache, so checking a question again
costs nothing. Questions already run in calibration are cached too.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.config import REPO_ROOT  # noqa: E402
from verdict.data.loaders import load_bird_dev  # noqa: E402
from verdict.engine.generate import build_prompt, parse_reply  # noqa: E402
from verdict.engine.group import run_and_group  # noqa: E402
from verdict.engine.llm import GeminiWriter, LLMError  # noqa: E402
from verdict.engine.schema import describe_schema  # noqa: E402
from verdict.engine.trust import decide  # noqa: E402
from verdict.verifier.compare import compare_results  # noqa: E402
from verdict.verifier.pool import execute_isolated  # noqa: E402

LEVEL = {"green": "GREEN (trusted)", "yellow": "YELLOW (check it)",
         "red": "RED (no answer shown)", "unanswerable": "CANNOT ANSWER"}


def short(sql: str, width: int = 110) -> str:
    s = " ".join(sql.split())
    return s if len(s) <= width else s[: width - 3] + "..."


def rows(result, limit: int = 3) -> str:
    if not result.ok:
        return f"{result.status}: {result.error}"
    more = f"  ... ({len(result.rows)} rows)" if len(result.rows) > limit else ""
    return f"{list(result.rows[:limit])}{more}"


def check(task, writer) -> dict:
    line = "=" * 78
    print(f"\n{line}\n Question {task.question_id}   ({task.db_id}, {task.difficulty})\n{line}")

    print("\n STEP 1  The BIRD question")
    print(f"   Question: {task.question}")
    print(f"   Hint:     {task.evidence or '-'}")

    print("\n STEP 2  Ask the AI 8 times")
    prompt = build_prompt(describe_schema(task.db_path), task.question, task.evidence)
    attempts = [parse_reply(r) for r in writer.write(prompt, 8)]
    for i, a in enumerate(attempts, 1):
        print(f"   {i}. {short(a.sql) if a.sql else a.kind}")

    print("\n STEP 3  Run them, group equal answers, decide trust")
    g = run_and_group(attempts, task.db_path, timeout_s=20)
    for k, grp in enumerate(g.groups, 1):
        print(f"   Group {k}: {grp.size}/8 attempts -> {rows(grp.result)}")
    if g.n_failed or g.n_cannot_answer:
        print(f"   Failed: {g.n_failed}   Said CANNOT_ANSWER: {g.n_cannot_answer}")
    d = decide(g)
    print(f"   Trust: {LEVEL[d.level]}  ({d.reason})")

    print("\n STEP 4  Open the answer key")
    gold = execute_isolated(task.gold_sql, task.db_path, timeout_s=60)
    print(f"   Gold SQL:    {short(task.gold_sql)}")
    print(f"   Gold answer: {rows(gold)}")

    print("\n STEP 5  Was the engine right?")
    if g.top is None:
        right = None
        print("   No answer to compare (nothing ran).")
    elif not gold.ok:
        right = None
        print("   The gold SQL itself failed, so this question cannot be scored.")
    else:
        right = compare_results(g.top.result, gold, task.gold_sql).verdict == "correct"
        print(f"   Engine's answer: {rows(g.top.result)}")
        print(f"   {'RIGHT' if right else 'WRONG'}"
              + ("" if right or d.level != "green" else "   <- trusted but wrong: the case to worry about"))
    return {"id": task.question_id, "agree": g.top.size if g.top else 0, "level": d.level, "right": right}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ids", nargs="*", type=int, help="BIRD dev question ids")
    p.add_argument("--random", type=int, default=0, help="check N random questions")
    p.add_argument("--model", default="gemini-3.5-flash-lite")
    args = p.parse_args()

    dev = {t.question_id: t for t in load_bird_dev()}
    ids = list(args.ids) + random.sample(sorted(dev), args.random)
    if not ids:
        sys.exit("Give question ids (e.g. 733 82) or --random 5")
    missing = [i for i in ids if i not in dev]
    if missing:
        sys.exit(f"Not in BIRD dev: {missing} (ids go from 0 to {max(dev)})")

    writer = GeminiWriter(model=args.model, cache_dir=REPO_ROOT / "scratch" / "llm_cache")
    register = []
    for i in ids:
        try:
            register.append(check(dev[i], writer))
        except LLMError as e:
            print(f"\n Stopped: could not reach the AI. {e}")
            break

    if len(register) > 1:
        print(f"\n{'=' * 78}\n REGISTER\n{'=' * 78}")
        print("   Question   Agree   Trust        Right?")
        for r in register:
            ok = {True: "right", False: "WRONG", None: "-"}[r["right"]]
            print(f"   {r['id']:>8}   {r['agree']}/8     {r['level']:<12} {ok}")
        green = [r for r in register if r["level"] == "green" and r["right"] is not None]
        if green:
            print(f"\n   GREEN answers right: {sum(r['right'] for r in green)} of {len(green)}")


if __name__ == "__main__":
    main()
