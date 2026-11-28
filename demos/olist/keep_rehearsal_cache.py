"""Keep the cached answers from a demo rehearsal, so the stage run is instant.

    python demos/olist/keep_rehearsal_cache.py --rehearsed data/app.rehearsed.db --into data/app.db

Why: the answer cache key includes the database's knowledge version. On stage,
approving the review item raises olist's version from 0 to 1, so the similar
question after it would run fresh (20 to 60 seconds on the laptop). In the
rehearsal the same approval made the same version 1, and the similar question
was cached under it. This copies those cache rows into the clean copy of the
app database, and changes nothing else: no asks, no review items, no knowledge.

Only use it when the stage run does exactly what the rehearsal did (same
questions, same single approval). Any other knowledge change on stage gives a
different version, and the copied rows are simply not used.

Stop the server before running this. A backup of --into is written first.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rehearsed", type=Path, required=True, help="app database after the rehearsal")
    ap.add_argument("--into", type=Path, required=True, help="clean app database used on stage")
    args = ap.parse_args()
    for p in (args.rehearsed, args.into):
        if not p.is_file():
            raise SystemExit(f"not found: {p}")

    backup = args.into.with_name(args.into.stem + ".before-keep" + args.into.suffix)
    shutil.copy2(args.into, backup)
    with closing(sqlite3.connect(args.into)) as con:
        con.execute("ATTACH DATABASE ? AS r", (str(args.rehearsed),))
        before = con.execute("SELECT COUNT(*) FROM ask_cache").fetchone()[0]
        con.execute("INSERT OR IGNORE INTO ask_cache SELECT * FROM r.ask_cache")
        con.commit()
        after = con.execute("SELECT COUNT(*) FROM ask_cache").fetchone()[0]
        versions = con.execute("SELECT database_id, version FROM knowledge_versions").fetchall()
    print(f"cache rows: {before} -> {after} (backup: {backup})")
    print(f"knowledge versions in --into (should be the pre-rehearsal ones): {versions}")


if __name__ == "__main__":
    main()
