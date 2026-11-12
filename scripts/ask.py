"""Ask a question about a file from the terminal.

    python scripts/ask.py sales.csv "What is the total sales in Pune?"
    python scripts/ask.py uploads/ab12cd.sqlite "Which city sold the most?" --show-attempts

CSV and Excel files are turned into a database first (engine/ingest.py).
Needs GEMINI_API_KEY in .env. --model overrides GEMINI_MODEL, e.g.
--model gemini-3.5-flash-lite.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.engine.ask import ask  # noqa: E402
from verdict.engine.ingest import SQLITE_EXTS, ingest  # noqa: E402
from verdict.engine.llm import GeminiWriter, LLMError  # noqa: E402

ICON = {"green": "GREEN  (trusted)", "yellow": "YELLOW (check it)", "red": "RED    (no answer)",
        "unanswerable": "CANNOT ANSWER from this data"}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="CSV, Excel or SQLite file")
    p.add_argument("question")
    p.add_argument("-n", type=int, default=8, help="number of attempts (default 8)")
    p.add_argument("--model", default=None, help="Gemini model (default: GEMINI_MODEL in .env)")
    p.add_argument("--show-attempts", action="store_true", help="print every attempt and its group")
    args = p.parse_args()

    src = Path(args.file)
    if src.suffix.lower() in SQLITE_EXTS:
        db = src
    else:
        db = ingest(src).db_path
        print(f"Built database: {db}")

    try:
        a = ask(db, args.question, writer=GeminiWriter(model=args.model), n=args.n)
    except LLMError as e:
        sys.exit(f"\nCould not get answers from the AI, so no trust level was given.\n{e}")

    print(f"\nQuestion: {a.question}")
    print(f"Trust:    {ICON[a.level]}  - {a.reason}")
    if a.shown:
        print(f"Columns:  {', '.join(a.columns)}")
        for row in a.rows[:20]:
            print(f"          {row}")
        if len(a.rows) > 20:
            print(f"          ... {len(a.rows) - 20} more rows")
        print(f"SQL:      {a.sql}")

    if args.show_attempts:
        print("\nAttempts:")
        group_of = {i: gi for gi, g in enumerate(a.grouping.groups) for i in g.members}
        for i, att in enumerate(a.attempts):
            r = a.grouping.results[i]
            if att.kind != "sql":
                tag = att.kind
            elif r is not None and not r.ok:
                tag = f"failed ({r.status})"
            else:
                tag = f"group {group_of[i] + 1}"
            print(f"  {i + 1}. [{tag}] {att.sql or att.raw[:80]!r}")


if __name__ == "__main__":
    main()
