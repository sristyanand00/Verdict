"""The app's own database: data/app.db.

Holds everything Verdict remembers between requests:

    databases       uploaded databases (preloaded ones are listed in code)
    asks            every question asked, with its full verdict (the audit trail)
    review_items    the analyst's review queue
    meanings        "revenue = SUM(payment_value), delivered orders only"
    examples        approved question + SQL pairs, used as prompt examples
    known_numbers   approved answers that later answers must not contradict
    settings        current database, model, second model on/off

This file is separate from the user databases. Those are only ever opened
read-only through the verifier; this one is the only file Verdict writes to.

Each call opens its own short connection. FastAPI runs requests on several
threads, and SQLite connections must not be shared between threads.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verdict.config import REPO_ROOT

SCHEMA = """
CREATE TABLE IF NOT EXISTS databases (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL,
    source TEXT NOT NULL, tables_count INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asks (
    id TEXT PRIMARY KEY, database_id TEXT NOT NULL, question TEXT NOT NULL,
    model TEXT NOT NULL, level TEXT NOT NULL, answer_text TEXT,
    response TEXT NOT NULL, latency_ms INTEGER NOT NULL, created_at TEXT NOT NULL,
    flagged INTEGER NOT NULL DEFAULT 0, flag_note TEXT
);
CREATE INDEX IF NOT EXISTS asks_created ON asks(created_at);
CREATE TABLE IF NOT EXISTS review_items (
    id TEXT PRIMARY KEY, ask_id TEXT NOT NULL REFERENCES asks(id),
    source TEXT NOT NULL, status TEXT NOT NULL,
    final_sql TEXT, final_columns TEXT, final_rows TEXT, note TEXT,
    created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS review_status ON review_items(status);
CREATE TABLE IF NOT EXISTS meanings (
    id TEXT PRIMARY KEY, database_id TEXT NOT NULL, term TEXT NOT NULL,
    definition TEXT NOT NULL, sql_hint TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS examples (
    id TEXT PRIMARY KEY, database_id TEXT NOT NULL, question TEXT NOT NULL,
    sql TEXT NOT NULL, columns TEXT NOT NULL, rows TEXT NOT NULL,
    from_review_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS known_numbers (
    id TEXT PRIMARY KEY, database_id TEXT NOT NULL, name TEXT NOT NULL,
    question TEXT NOT NULL, sql TEXT NOT NULL, columns TEXT NOT NULL,
    value TEXT NOT NULL, created_at TEXT NOT NULL,
    last_checked_at TEXT, last_ok INTEGER
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

#: Columns stored as JSON text, decoded on the way out.
_JSON_COLS = {"response", "final_columns", "final_rows", "columns", "rows", "value"}


def default_path() -> Path:
    env = os.environ.get("VERDICT_APP_DB")
    return Path(env).expanduser().resolve() if env else REPO_ROOT / "data" / "app.db"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _dump(v: Any) -> str:
    # default=str keeps odd values (dates, bytes) from breaking a save.
    return json.dumps(v, default=str)


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con, con:
            con.executescript(SCHEMA)

    # -- plumbing ----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        for k in _JSON_COLS & d.keys():
            if d[k] is not None:
                d[k] = json.loads(d[k])
        return d

    def _all(self, sql: str, args: tuple = ()) -> list[dict]:
        with closing(self._connect()) as con:
            return [self._row(r) for r in con.execute(sql, args)]

    def _one(self, sql: str, args: tuple = ()) -> dict | None:
        with closing(self._connect()) as con:
            return self._row(con.execute(sql, args).fetchone())

    def _run(self, sql: str, args: tuple = ()) -> int:
        with closing(self._connect()) as con, con:
            return con.execute(sql, args).rowcount

    def ok(self) -> bool:
        try:
            self._one("SELECT 1 AS x")
            return True
        except sqlite3.Error:
            return False

    # -- databases (uploads) -------------------------------------------------

    def add_database(self, name: str, path: str, source: str, tables_count: int) -> dict:
        db_id = new_id("up")
        self._run(
            "INSERT INTO databases VALUES (?, ?, ?, ?, ?, ?)",
            (db_id, name, path, source, tables_count, now()),
        )
        return self.get_database(db_id)

    def get_database(self, db_id: str) -> dict | None:
        return self._one("SELECT * FROM databases WHERE id = ?", (db_id,))

    def list_databases(self) -> list[dict]:
        return self._all("SELECT * FROM databases ORDER BY created_at")

    # -- asks ----------------------------------------------------------------

    def save_ask(self, response: dict) -> None:
        """Save one full /api/ask response. ``response['ask_id']`` is the key."""
        self._run(
            "INSERT INTO asks (id, database_id, question, model, level, answer_text, response,"
            " latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                response["ask_id"], response["database_id"], response["question"],
                response["model"], response["level"], response.get("answer_text"),
                _dump(response), int(response.get("latency_ms", 0)), response["created_at"],
            ),
        )

    def get_ask(self, ask_id: str) -> dict | None:
        row = self._one("SELECT * FROM asks WHERE id = ?", (ask_id,))
        if row is None:
            return None
        resp = row["response"]
        resp["flagged"] = bool(row["flagged"])
        resp["flag_note"] = row["flag_note"]
        return resp

    def list_asks(self, limit: int = 20, database_id: str | None = None) -> list[dict]:
        where, args = ("WHERE database_id = ?", (database_id,)) if database_id else ("", ())
        rows = self._all(
            f"SELECT id, database_id, question, level, answer_text, created_at, flagged FROM asks"
            f" {where} ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (*args, int(limit)),
        )
        return [
            {"ask_id": r["id"], "database_id": r["database_id"], "question": r["question"],
             "level": r["level"], "answer_text": r["answer_text"], "created_at": r["created_at"],
             "flagged": bool(r["flagged"])}
            for r in rows
        ]

    def flag_ask(self, ask_id: str, note: str) -> None:
        self._run("UPDATE asks SET flagged = 1, flag_note = ? WHERE id = ?", (note, ask_id))

    def count_asks_since(self, since: str) -> dict[str, int]:
        rows = self._all(
            "SELECT level, COUNT(*) AS n FROM asks WHERE created_at >= ? GROUP BY level", (since,)
        )
        return {r["level"]: r["n"] for r in rows}

    # -- review queue --------------------------------------------------------

    def add_review_item(self, ask_id: str, source: str = "auto") -> dict:
        item_id = new_id("r")
        self._run(
            "INSERT INTO review_items (id, ask_id, source, status, created_at) VALUES (?, ?, ?, 'open', ?)",
            (item_id, ask_id, source, now()),
        )
        return self.get_review_item(item_id)

    def get_review_item(self, item_id: str) -> dict | None:
        return self._one("SELECT * FROM review_items WHERE id = ?", (item_id,))

    def open_item_for_ask(self, ask_id: str) -> dict | None:
        return self._one(
            "SELECT * FROM review_items WHERE ask_id = ? AND status = 'open'", (ask_id,)
        )

    def list_review_items(
        self, status: str | None = None, level: str | None = None, database_id: str | None = None
    ) -> list[dict]:
        sql = (
            "SELECT r.*, a.question, a.level, a.database_id, a.response FROM review_items r"
            " JOIN asks a ON a.id = r.ask_id WHERE 1 = 1"
        )
        args: list = []
        for col, val in (("r.status", status), ("a.level", level), ("a.database_id", database_id)):
            if val:
                sql += f" AND {col} = ?"
                args.append(val)
        sql += " ORDER BY r.created_at DESC, r.rowid DESC"
        return self._all(sql, tuple(args))

    def resolve_review_item(
        self, item_id: str, status: str, final_sql: str | None,
        final_columns: list | None, final_rows: list | None, note: str | None,
    ) -> dict | None:
        self._run(
            "UPDATE review_items SET status = ?, final_sql = ?, final_columns = ?, final_rows = ?,"
            " note = ?, resolved_at = ? WHERE id = ?",
            (
                status, final_sql,
                None if final_columns is None else _dump(final_columns),
                None if final_rows is None else _dump(final_rows),
                note, now(), item_id,
            ),
        )
        return self.get_review_item(item_id)

    def review_counts(self) -> dict[str, int]:
        rows = self._all(
            "SELECT a.level, COUNT(*) AS n FROM review_items r JOIN asks a ON a.id = r.ask_id"
            " WHERE r.status = 'open' GROUP BY a.level"
        )
        return {r["level"]: r["n"] for r in rows}

    # -- knowledge -----------------------------------------------------------

    def add_meaning(self, database_id: str, term: str, definition: str, sql_hint: str | None = None) -> dict:
        mid = new_id("m")
        self._run(
            "INSERT INTO meanings VALUES (?, ?, ?, ?, ?, ?)",
            (mid, database_id, term.strip(), definition.strip(), sql_hint, now()),
        )
        return self._one("SELECT * FROM meanings WHERE id = ?", (mid,))

    def add_example(
        self, database_id: str, question: str, sql: str, columns: list, rows: list,
        from_review_id: str | None = None,
    ) -> dict:
        eid = new_id("e")
        self._run(
            "INSERT INTO examples VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, database_id, question.strip(), sql, _dump(columns), _dump(rows), from_review_id, now()),
        )
        return self._one("SELECT * FROM examples WHERE id = ?", (eid,))

    def add_known_number(
        self, database_id: str, name: str, question: str, sql: str, columns: list, value: list
    ) -> dict:
        kid = new_id("k")
        self._run(
            "INSERT INTO known_numbers (id, database_id, name, question, sql, columns, value,"
            " created_at, last_checked_at, last_ok) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (kid, database_id, name.strip(), question.strip(), sql, _dump(columns), _dump(value), now(), now()),
        )
        return self.get_known_number(kid)

    def get_known_number(self, kid: str) -> dict | None:
        return self._one("SELECT * FROM known_numbers WHERE id = ?", (kid,))

    def mark_known_checked(self, kid: str, ok: bool) -> None:
        self._run(
            "UPDATE known_numbers SET last_checked_at = ?, last_ok = ? WHERE id = ?",
            (now(), int(ok), kid),
        )

    def knowledge(self, database_id: str) -> dict[str, list[dict]]:
        q = "SELECT * FROM {} WHERE database_id = ? ORDER BY created_at"
        return {
            "meanings": self._all(q.format("meanings"), (database_id,)),
            "examples": self._all(q.format("examples"), (database_id,)),
            "known_numbers": self._all(q.format("known_numbers"), (database_id,)),
        }

    _KINDS = {"meanings": "meanings", "examples": "examples", "known": "known_numbers"}

    def delete_knowledge(self, kind: str, item_id: str) -> bool:
        table = self._KINDS.get(kind)
        if table is None:
            raise ValueError(f"unknown knowledge kind: {kind}")
        return self._run(f"DELETE FROM {table} WHERE id = ?", (item_id,)) > 0

    # -- settings ------------------------------------------------------------

    def get_settings(self) -> dict[str, Any]:
        # _row already decodes the "value" column.
        return {r["key"]: r["value"] for r in self._all("SELECT key, value FROM settings")}

    def put_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        with closing(self._connect()) as con, con:
            for k, v in values.items():
                con.execute(
                    "INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (k, _dump(v)),
                )
        return self.get_settings()
