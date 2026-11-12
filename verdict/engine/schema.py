"""Step 1 of the trust engine: describe the database to the AI.

    describe_schema(db_path) -> "sales(order_date TEXT, amount REAL, city TEXT)"

The AI cannot see the database. It writes SQL from this description alone, so
the description must name every table and column exactly.

Only names and types are sent, never rows. The user's data stays on our
server; the AI provider sees the shape of the data, not the data itself. This
is different from verdict/data/schema.py, which adds sample rows for training
on the public BIRD benchmark, where privacy is not a concern.

Trade-off: without sample rows the AI cannot know whether a city is stored as
"Pune" or "pune". The trust engine catches some of these mistakes (an empty
answer is never shown as trusted), but not all of them.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from verdict.engine.ingest import SQL_KEYWORDS
from verdict.verifier.safety import read_only_uri


def _quote(name: str) -> str:
    """Quote a name only when it needs it, so the common case stays readable.

    SQL keywords need quotes too: BIRD has a table called "order".
    """
    if name.isidentifier() and name.lower() == name and name not in SQL_KEYWORDS:
        return name
    return '"' + name.replace('"', '""') + '"'


def describe_schema(db_path: str | Path) -> str:
    """Return one line per table: ``table(col TYPE, col TYPE, ...)``.

    Raises FileNotFoundError if the database does not exist, and ValueError if
    it has no tables, because neither can answer any question.
    """
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")

    # Read-only: describing the database must never be able to change it.
    with closing(sqlite3.connect(read_only_uri(db_path), uri=True)) as con:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        if not tables:
            raise ValueError(f"database has no tables: {db_path.name}")

        lines = []
        for table in tables:
            cols = con.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
            # PRAGMA table_info rows: (index, name, type, notnull, default, pk)
            parts = [f"{_quote(c[1])} {c[2] or 'TEXT'}".strip() for c in cols]
            lines.append(f"{_quote(table)}({', '.join(parts)})")

    return "\n".join(lines)
