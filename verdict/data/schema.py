"""Database schema text for training prompts.

For each table: its CREATE TABLE statement followed by a few sample rows, so
the model sees both the structure and what the values look like.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from verdict.verifier.safety import read_only_uri


def get_schema(db_path: Path, num_samples: int = 3) -> str:
    """Return every table's CREATE statement plus ``num_samples`` rows.

    Example output::

        CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
        -- Sample rows:
        -- (1, 'Alice')
        -- (2, 'Bob')
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")

    with closing(sqlite3.connect(read_only_uri(db_path), uri=True)) as con:
        tables = con.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        if not tables:
            return "-- Empty database (no tables found)"

        parts = []
        for name, create_sql in tables:
            parts.append(create_sql + ";")
            # Quoted because BIRD table names can contain spaces or keywords.
            quoted = '"' + name.replace('"', '""') + '"'
            try:
                rows = con.execute(f"SELECT * FROM {quoted} LIMIT ?", (num_samples,)).fetchall()
            except sqlite3.Error as e:
                parts.append(f"-- Error reading samples: {e}")
            else:
                if rows:
                    parts.append("-- Sample rows:")
                    parts.extend(f"-- {row}" for row in rows)
                else:
                    parts.append("-- (empty table)")
            parts.append("")

    return "\n".join(parts)


def get_schema_cached(db_path: Path, cache_dir: Path | None = None) -> str:
    """``get_schema`` with an on-disk cache that is rebuilt when the database changes."""
    if cache_dir is None:
        return get_schema(db_path)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{Path(db_path).stem}.schema.txt"

    if cache_file.exists() and cache_file.stat().st_mtime > Path(db_path).stat().st_mtime:
        return cache_file.read_text(encoding="utf-8")

    schema = get_schema(db_path)
    cache_file.write_text(schema, encoding="utf-8")
    return schema
