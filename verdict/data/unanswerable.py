"""Build BIRD questions that are provably unanswerable.

    make_unanswerable(tasks, k=50) -> list[BirdTask]

Take a real BIRD question, copy its database, and drop every table the gold
SQL reads. The question stays the same, but the data it needs is gone, so the
right reply is "this data cannot answer the question". The other tables stay,
so the model still sees a realistic database and can be tempted to answer
from the wrong tables.

Why not hand-write questions like "how happy are customers?": those are easy
to spot as off-topic. These questions are on-topic for the database and were
answerable a moment ago, which is the hard case for a trust engine.

Copies are written under <data root>/unanswerable/ (gitignored with the rest
of datasets/) and reused across runs. Large databases are skipped so the
copies stay small.
"""

from __future__ import annotations

import random
import shutil
import sqlite3
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import sqlglot
from sqlglot import exp

from verdict import config
from verdict.data.loaders import BirdTask

#: Databases above this size are not copied.
MAX_DB_MB = 70


def gold_tables(sql: str) -> set[str]:
    """Lower-cased names of the tables a query reads (CTE names excluded)."""
    tree = sqlglot.parse_one(sql, read="sqlite")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    return {t.name.lower() for t in tree.find_all(exp.Table)} - ctes


def db_tables(db_path: Path) -> list[str]:
    con = sqlite3.connect(db_path)
    try:
        return [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]
    finally:
        con.close()


def _copy_without(src: Path, drop: list[str], out_root: Path) -> Path:
    """Copy ``src`` and drop ``drop`` from the copy. Reuses an existing copy."""
    name = f"{src.stem}__minus__{'_'.join(sorted(t.lower() for t in drop))}"
    dst = out_root / name / f"{name}.sqlite"
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    shutil.copyfile(src, tmp)
    con = sqlite3.connect(tmp)
    try:
        con.execute("PRAGMA foreign_keys = OFF")
        for t in drop:
            con.execute(f'DROP TABLE "{t.replace(chr(34), chr(34) * 2)}"')
        con.commit()
    finally:
        con.close()
    tmp.replace(dst)  # only a finished copy gets the real name
    return dst


def make_unanswerable(
    tasks: list[BirdTask],
    k: int = 50,
    seed: int = 0,
    out_root: str | Path | None = None,
    max_db_mb: float = MAX_DB_MB,
) -> list[BirdTask]:
    """Return up to ``k`` tasks whose database no longer has the tables they need.

    Tasks are drawn round-robin across databases so no single database
    dominates. The returned tasks keep their question and evidence; gold_sql
    is "" because there is no right query.
    """
    out_root = Path(out_root) if out_root else config.data_root() / "unanswerable"
    rng = random.Random(seed)

    by_db: dict[str, list[BirdTask]] = defaultdict(list)
    for t in tasks:
        if t.db_path.stat().st_size / 1e6 <= max_db_mb:
            by_db[t.db_id].append(t)
    for lst in by_db.values():
        rng.shuffle(lst)

    tables_of = {db: db_tables(lst[0].db_path) for db, lst in by_db.items()}
    picked: list[BirdTask] = []
    queues = sorted(by_db)
    while len(picked) < k and any(by_db[d] for d in queues):
        for db in queues:
            if len(picked) >= k or not by_db[db]:
                continue
            task = by_db[db].pop()
            try:
                used = gold_tables(task.gold_sql)
            except Exception:
                continue
            drop = [t for t in tables_of[db] if t.lower() in used]
            keep = [t for t in tables_of[db] if t.lower() not in used]
            if not drop or not keep:  # nothing to remove, or nothing left
                continue
            path = _copy_without(task.db_path, drop, out_root)
            picked.append(replace(task, gold_sql="", db_path=path, db_id=path.stem))
    return picked
