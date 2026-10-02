"""Try the verifier by hand on the small test database.

    python scripts/play_verifier.py          # show the database, then type queries
    python scripts/play_verifier.py --demo   # run a fixed set of examples

The database is written to scratch/tiny/tiny.sqlite so it can also be opened
in DB Browser for SQLite.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fixtures import make_tiny_db  # noqa: E402
from verdict.train.reward import SQLRewardFunction  # noqa: E402
from verdict.verifier.compare import compare_results  # noqa: E402
from verdict.verifier.execute import execute_query  # noqa: E402

DB_DIR = ROOT / "scratch"
DEFAULT_GOLD = "SELECT name FROM students WHERE year = 2"

DEMO = [
    ("right answer", "SELECT name FROM students WHERE year = 2"),
    ("same rows, other order", "SELECT name FROM students WHERE year = 2 ORDER BY name DESC"),
    ("wrong answer", "SELECT name FROM students WHERE year = 3"),
    ("broken SQL", "SELECT nonsense FROM nowhere"),
    ("attack", "DROP TABLE students"),
    ("never ends", "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c"),
]


def fresh_db() -> Path:
    db = DB_DIR / "tiny" / "tiny.sqlite"
    if db.exists():
        db.unlink()  # rebuild so every run starts from the same known data
    return make_tiny_db(DB_DIR)


def show_table(db: Path, table: str) -> None:
    r = execute_query(f"SELECT * FROM {table}", db, use_first_pass_filter=False)
    print(f"\n  {table}")
    print("  " + " | ".join(f"{c:<10}" for c in r.columns))
    print("  " + "-" * (13 * len(r.columns)))
    for row in r.rows:
        print("  " + " | ".join(f"{'NULL' if v is None else v!s:<10}" for v in row))


def check(db: Path, candidate: str, gold: str) -> None:
    cand = execute_query(candidate, db, timeout_s=2.0)
    gold_r = execute_query(gold, db, timeout_s=2.0, use_first_pass_filter=False)
    v = compare_results(cand, gold_r, gold)
    score = SQLRewardFunction(DB_DIR, timeout_s=2.0)(
        ["q"], [candidate], gold_sql=[gold], db_id=["tiny"]
    )[0]

    print(f"  candidate : {candidate}")
    print(f"  status    : {cand.status}  ({cand.elapsed_ms:.0f} ms)")
    if cand.error:
        print(f"  error     : {cand.error}")
    print(f"  rows      : {list(cand.rows)}")
    print(f"  gold rows : {list(gold_r.rows)}")
    print(f"  verdict   : {v.verdict}  ({v.reason})")
    print(f"  score     : {score}")


def main() -> None:
    db = fresh_db()
    print(f"Database: {db}")
    show_table(db, "students")
    show_table(db, "marks")

    if "--demo" in sys.argv:
        print(f"\nGold query: {DEFAULT_GOLD}")
        for name, sql in DEMO:
            print(f"\n--- {name} ---")
            check(db, sql, DEFAULT_GOLD)
        return

    gold = DEFAULT_GOLD
    print(f"\nGold query: {gold}")
    print("Type a SQL query and press Enter.  'gold <sql>' changes the gold query.  'q' quits.")
    while True:
        try:
            line = input("\nsql> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line.lower() in ("q", "quit", "exit"):
            break
        if line.lower().startswith("gold "):
            gold = line[5:].strip()
            print(f"  gold is now: {gold}")
            continue
        if line:
            check(db, line, gold)


if __name__ == "__main__":
    main()
