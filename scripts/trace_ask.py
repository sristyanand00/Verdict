"""Watch the trust engine work, one step at a time.

Runs the same steps as verdict.engine.ask.ask(), but prints what each step
receives and produces, so you can see inside the engine.

    python scripts/trace_ask.py sales.csv "What is the total sales in Pune?"
    python scripts/trace_ask.py sales.csv "Which city sold the most laptops?" --pause
    python scripts/trace_ask.py sales.csv "Total sales in Pune?" --offline

--pause    wait for Enter after each step
--offline  no Gemini: use 8 pre-written replies (a mix of right, wrong and
           broken SQL), so you can test without an API key or quota
--no-cache always ask Gemini again (by default replies are saved in
           scratch/llm_cache, so re-running the same question is free)
--model    Gemini model to use, e.g. gemini-3.5-flash-lite
           (default: GEMINI_MODEL from .env)
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.config import REPO_ROOT  # noqa: E402
from verdict.engine.generate import build_prompt, parse_reply  # noqa: E402
from verdict.engine.group import run_and_group  # noqa: E402
from verdict.engine.ingest import SQLITE_EXTS, ingest  # noqa: E402
from verdict.engine.llm import FixedWriter, GeminiWriter, LLMError  # noqa: E402
from verdict.engine.schema import describe_schema  # noqa: E402
from verdict.engine.trust import decide, load_thresholds  # noqa: E402

PAUSE = False

#: Offline replies for the demo: 5 correct, 1 with a wrong filter,
#: 1 broken (bad column), 1 that refuses.
OFFLINE_REPLIES = [
    "```sql\nSELECT SUM(amount) FROM sales WHERE city = 'Pune'\n```",
    "```sql\nSELECT SUM(amount) FROM sales WHERE city = 'Pune';\n```",
    "```sql\nSELECT TOTAL(amount) FROM sales WHERE city = 'Pune'\n```",
    "Sure.\n```sql\nSELECT SUM(amount) AS total FROM sales WHERE city IN ('Pune')\n```",
    "```sql\nSELECT SUM(s.amount) FROM sales s WHERE s.city = 'Pune'\n```",
    "```sql\nSELECT SUM(amount) FROM sales WHERE city = 'Mumbai'\n```",
    "```sql\nSELECT SUM(price) FROM sales WHERE city = 'Pune'\n```",
    "CANNOT_ANSWER",
]


def step(n: int, title: str, why: str) -> None:
    if PAUSE and n > 0:
        input("\n   [Enter] next step ... ")
    print("\n" + "=" * 72)
    print(f" STEP {n}: {title}")
    print("=" * 72)
    print(textwrap.fill(f"Why: {why}", 72, initial_indent="   ", subsequent_indent="   "))
    print()


def show(text: str, indent: str = "   | ") -> None:
    for line in text.splitlines() or [""]:
        print(indent + line)


def one_line(sql: str, width: int = 60) -> str:
    s = " ".join(sql.split())
    return s if len(s) <= width else s[: width - 3] + "..."


def main() -> None:
    global PAUSE
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="CSV, Excel or SQLite file")
    p.add_argument("question")
    p.add_argument("-n", type=int, default=8)
    p.add_argument("--pause", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--model", default=None, help="Gemini model (default: GEMINI_MODEL in .env)")
    args = p.parse_args()
    PAUSE = args.pause

    # ---------------------------------------------------------------- 0
    step(0, "Turn the file into a database   (engine/ingest.py)",
         "SQL needs a database. The upload is copied into a new SQLite file, so the "
         "original is never touched, and column names are cleaned so the AI can write them.")
    src = Path(args.file)
    if src.suffix.lower() in SQLITE_EXTS:
        db = src
        print(f"   Already a database: {db}")
    else:
        res = ingest(src)
        db = res.db_path
        print(f"   Built: {db}")
        for table, rows in res.tables.items():
            print(f"   Table '{table}': {rows} rows")
            renamed = {k: v for k, v in res.columns[table].items() if k != v}
            for clean, orig in renamed.items():
                print(f"      column {orig!r:>16} -> {clean}")

    # ---------------------------------------------------------------- 1
    step(1, "Describe the tables   (engine/schema.py)",
         "The AI never sees the database. It writes SQL from this description alone. "
         "Only names and types are sent, never row values, so the user's data stays here.")
    schema = describe_schema(db)
    show(schema)

    # ---------------------------------------------------------------- 2a
    step(2, "Build the prompt   (engine/generate.py)",
         "The prompt gives the AI a way out (CANNOT_ANSWER). Without it, the AI "
         "writes some SQL for every question and some number comes back.")
    prompt = build_prompt(schema, args.question)
    show(prompt)

    # ---------------------------------------------------------------- 2b
    step(3, f"Ask the AI {args.n} times   (engine/llm.py)",
         "One answer can be confidently wrong. Several independent attempts let us "
         "measure agreement. Temperature 0.8 lets the attempts differ.")
    if args.offline:
        writer = FixedWriter(OFFLINE_REPLIES)
        print("   OFFLINE: using pre-written replies instead of Gemini.\n")
    else:
        cache = None if args.no_cache else REPO_ROOT / "scratch" / "llm_cache"
        writer = GeminiWriter(model=args.model, cache_dir=cache)
        print(f"   Model: {writer.model}" + ("   (cached replies reused)" if cache else "") + "\n")
    try:
        replies = writer.write(prompt, args.n)
    except LLMError as e:
        sys.exit(f"   Could not get answers from the AI, so no trust level is given.\n   {e}")
    for i, r in enumerate(replies, 1):
        print(f"   Reply {i}: {one_line(r, 62) if r else '(empty: the API call failed)'}")

    # ---------------------------------------------------------------- 2c
    step(4, "Read each reply   (engine/generate.py: parse_reply)",
         "Pull the SQL out of each reply. A reply is SQL, a refusal (CANNOT_ANSWER), or empty.")
    attempts = [parse_reply(r) for r in replies]
    for i, a in enumerate(attempts, 1):
        print(f"   {i}. {a.kind:<14} {one_line(a.sql) if a.sql else ''}")

    # ---------------------------------------------------------------- 3
    step(5, "Run every SQL safely and group equal answers   (engine/group.py + verifier)",
         "The answer is what the user sees, so attempts are grouped by result, not by SQL "
         "text. Each query runs read-only in its own process and is killed after 5 s.")
    g = run_and_group(attempts, db)
    for i, (a, r) in enumerate(zip(attempts, g.results), 1):
        if r is None:
            print(f"   {i}. not run ({a.kind})")
        elif r.ok:
            print(f"   {i}. ok      {str(r.rows[:3])[:40]:<40} {r.elapsed_ms:6.1f} ms")
        else:
            print(f"   {i}. {r.status:<7} {(r.error or '')[:55]}")
    print("\n   Groups (same answer = same group):")
    for k, grp in enumerate(g.groups, 1):
        bar = "#" * grp.size + "." * (g.n_attempts - grp.size)
        flag = "   <- empty answer" if grp.is_empty_answer else ""
        print(f"   Group {k}: [{bar}] {grp.size}/{g.n_attempts}  answer={str(grp.result.rows[:3])[:30]}{flag}")
        print(f"            attempts {[m + 1 for m in grp.members]}")
    print(f"\n   Refused (CANNOT_ANSWER): {g.n_cannot_answer}    Failed: {g.n_failed}")

    # ---------------------------------------------------------------- 4
    t = load_thresholds()
    step(6, "Decide how much to trust it   (engine/trust.py + thresholds.json)",
         "Trust comes from agreement: the share of attempts in the largest group. An "
         "empty answer is never green, because attempts can agree on the same mistake.")
    n = g.n_attempts
    print(f"   Rules (thresholds.json, placeholders until Phase 2 calibration):")
    print(f"     more than {t['cannot_answer']:.0%} refused  -> CANNOT ANSWER")
    print(f"     agreement >= {t['green']:.0%} ({t['green'] * n:.0f}/{n}) -> GREEN")
    print(f"     agreement >= {t['yellow']:.0%} ({t['yellow'] * n:.0f}/{n}) -> YELLOW")
    print(f"     otherwise              -> RED (no answer shown)\n")
    d = decide(g, t)
    print(f"   Refused {g.n_cannot_answer}/{n} = {g.n_cannot_answer / n:.0%}")
    if g.top:
        print(f"   Largest group {g.top.size}/{n} = {g.top.size / n:.0%}   empty answer: {g.top.is_empty_answer}")

    # ---------------------------------------------------------------- 5
    step(7, "Final answer   (engine/ask.py joins steps 1-6)", "This is what the user sees.")
    label = {"green": "GREEN  - trusted", "yellow": "YELLOW - check before using",
             "red": "RED    - not sure, no answer", "unanswerable": "CANNOT ANSWER from this data"}
    print(f"   Question: {args.question}")
    print(f"   Trust:    {label[d.level]}")
    print(f"   Reason:   {d.reason}")
    if d.answer:
        print(f"   Answer:   {d.answer.result.rows[:10]}")
        print(f"   SQL:      {one_line(d.answer.sqls[0], 70)}")
    print()


if __name__ == "__main__":
    main()
