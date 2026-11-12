"""Phase 2: measure how often each level of agreement is actually right.

    python scripts/run_calibration.py --model gemini-3.5-flash-lite
    python scripts/run_calibration.py --report-only            # re-score saved runs, no AI calls
    python scripts/run_calibration.py --report-only --write-thresholds

Steps:
  1. Sample --questions BIRD dev questions (fixed seed, so the same ones every time).
  2. Build --unanswerable questions by dropping the tables their gold SQL needs.
  3. Run the trust engine on all of them (n attempts each) and save raw records
     to results/calibration/*.jsonl. Re-running skips finished questions, so a
     run stopped by the API quota can just be started again.
  4. Fit thresholds on half the questions, report on the other half.
  5. --write-thresholds saves the fitted values to verdict/engine/thresholds.json.

Gemini replies are cached in scratch/llm_cache, so repeating a run is free.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.config import REPO_ROOT, results_root  # noqa: E402
from verdict.data.loaders import load_bird_dev  # noqa: E402
from verdict.data.unanswerable import make_unanswerable  # noqa: E402
from verdict.engine.llm import GeminiWriter, LLMError  # noqa: E402
from verdict.engine.trust import THRESHOLDS_FILE, load_thresholds  # noqa: E402
from verdict.eval import calibration as cal  # noqa: E402
from verdict.eval.harness import evaluate, load_records  # noqa: E402


def pct(x: dict) -> str:
    """'85% [77-91] (85/100)'"""
    if not x["n"]:
        return "  -"
    return f"{x['rate']:4.0%} [{x['low']:.0%}-{x['high']:.0%}] ({x['k']}/{x['n']})"


def print_summary(title: str, s: dict) -> None:
    a = s["answerable"]
    t = s["thresholds"]
    print(f"\n--- {title} ---  thresholds: green>={t['green']:.3f} yellow>={t['yellow']:.3f} "
          f"refuse>{t['cannot_answer']:.3f}")
    print(f"  Answerable questions: {a['questions']}")
    print(f"    Plain app (1 attempt, always shown)  accuracy {pct(a['single'])}")
    print(f"    Majority vote (always shown)         accuracy {pct(a['vote'])}")
    print(f"    Verdict GREEN only                   accuracy {pct(a['green']['accuracy'])}   "
          f"coverage {pct(a['green']['coverage'])}")
    print(f"    Verdict GREEN + YELLOW               accuracy {pct(a['shown']['accuracy'])}   "
          f"coverage {pct(a['shown']['coverage'])}")
    print(f"    Levels: {a['levels']}")
    cw = a["confident_wrong"]
    print(f"    Wrong answers shown as reliable: plain app {cw['single_app']}  vs  Verdict green {cw['verdict_green']}")
    print(f"    Right answers Verdict held back (red/refused): {a['withheld_but_right']}")
    for d, v in a["by_difficulty"].items():
        print(f"      {d:<12} n={v['questions']:<4} plain {pct(v['single'])}  "
              f"green acc {pct(v['green_accuracy'])} cov {pct(v['green_coverage'])}")
    u = s.get("unanswerable")
    if u:
        print(f"  Unanswerable questions: {u['questions']}")
        print(f"    Plain app gave an answer anyway      {pct(u['single_app_answered'])}")
        print(f"    Verdict said CANNOT ANSWER           {pct(u['refused'])}")
        print(f"    Verdict GREEN (confident, wrong)     {pct(u['green'])}")
        print(f"    Verdict YELLOW / RED                 {pct(u['yellow'])} / {pct(u['red'])}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--questions", type=int, default=200)
    p.add_argument("--unanswerable", type=int, default=50)
    p.add_argument("-n", type=int, default=8)
    p.add_argument("--model", default=None)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--green-target", type=float, default=0.85)
    p.add_argument("--yellow-target", type=float, default=0.60)
    p.add_argument("--out", default=str(results_root() / "calibration"))
    p.add_argument("--report-only", action="store_true", help="no AI calls; score saved records")
    p.add_argument("--write-thresholds", action="store_true")
    args = p.parse_args()

    out = Path(args.out)
    ans_path, una_path = out / "answerable.jsonl", out / "unanswerable.jsonl"

    if not args.report_only:
        dev = load_bird_dev()
        tasks = random.Random(args.seed).sample(dev, args.questions)
        una_tasks = make_unanswerable(dev, k=args.unanswerable, seed=args.seed)
        writer = GeminiWriter(model=args.model, cache_dir=REPO_ROOT / "scratch" / "llm_cache")
        print(f"Model {writer.model}, {args.n} attempts per question")
        try:
            print(f"\nAnswerable: {len(tasks)} BIRD dev questions")
            evaluate(tasks, writer, ans_path, n=args.n, answerable=True)
            print(f"\nUnanswerable: {len(una_tasks)} questions with their tables removed")
            evaluate(una_tasks, writer, una_path, n=args.n, answerable=False)
        except LLMError as e:
            print(f"\nStopped: {e}\nProgress is saved. Run the same command again later to continue.")

    records, unans = load_records(ans_path), load_records(una_path)
    if not records:
        sys.exit("No records yet.")
    bad_gold = [r for r in records if r["gold_status"] != "ok"]

    print("\n=== Agreement vs correctness (all answerable questions) ===")
    print("  agree   questions   largest group right        empty answers")
    for row in cal.agreement_table(records):
        print(f"  {row['agree']}/{row['of']}     {row['n']:>5}      {pct(row):<26} {row['empty']}")
    if bad_gold:
        print(f"  ({len(bad_gold)} questions skipped: gold SQL failed: "
              f"{sorted({r['gold_status'] for r in bad_gold})})")

    calib, test = cal.split(records, args.seed)
    u_calib, u_test = cal.split(unans, args.seed) if unans else ([], [])
    current = load_thresholds()
    fit = cal.choose_thresholds(calib, args.green_target, args.yellow_target)
    fitted = {"green": fit["green"], "yellow": fit["yellow"], "cannot_answer": current["cannot_answer"]}
    f = fit["fit"]
    print(f"\n=== Thresholds fitted on calibration half ({f['questions']} questions) ===")
    print(f"  green : {f['green_k']}/{f['n']} agree -> {f['green_fit_accuracy']:.0%} right "
          f"(target {f['green_target']:.0%}, {f['green_support']} questions)"
          + ("" if f["green_target_met"] else "   TARGET NOT MET: green turned off"))
    print(f"  yellow: {f['yellow_k']}/{f['n']} agree -> {f['yellow_fit_accuracy']:.0%} right "
          f"(target {f['yellow_target']:.0%}, {f['yellow_support']} questions)")

    s_current = cal.summarize(test, u_test, current)
    s_fitted = cal.summarize(test, u_test, fitted)
    print_summary("TEST half, current thresholds.json", s_current)
    print_summary("TEST half, fitted thresholds  <- headline", s_fitted)

    sweep = cal.cannot_answer_sweep(records, unans, current) if unans else []
    if sweep:
        print("\n=== Refusal rule: refuse when more than X of attempts say CANNOT_ANSWER (all questions) ===")
        for row in sweep:
            print(f"  X={row['cannot_answer']:<6} unanswerable caught {pct(row['unanswerable_caught']):<24} "
                  f"answerable wrongly refused {pct(row['answerable_refused'])}")

    report = {
        "date": date.today().isoformat(),
        "questions": len(records), "unanswerable": len(unans), "seed": args.seed,
        "agreement_table": cal.agreement_table(records),
        "fit": fit, "test_current": s_current, "test_fitted": s_fitted,
        "cannot_answer_sweep": sweep,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {out / 'report.json'}")

    if args.write_thresholds:
        data = {
            "source": (f"Fitted {date.today().isoformat()} by scripts/run_calibration.py on "
                       f"{f['questions']} BIRD dev questions (calibration half): green = lowest agreement "
                       f"with >= {f['green_target']:.0%} accuracy, yellow = >= {f['yellow_target']:.0%}. "
                       f"cannot_answer kept from the previous file."),
            **fitted,
        }
        THRESHOLDS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {THRESHOLDS_FILE}")


if __name__ == "__main__":
    main()
