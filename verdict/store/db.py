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
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
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
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
    balance INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credit_ledger (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), at TEXT NOT NULL,
    kind TEXT NOT NULL, amount INTEGER NOT NULL, balance_after INTEGER NOT NULL,
    ask_id TEXT, question TEXT, note TEXT
);
CREATE INDEX IF NOT EXISTS ledger_user ON credit_ledger(user_id, at);
CREATE TABLE IF NOT EXISTS saved (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, ask_id TEXT NOT NULL, name TEXT NOT NULL,
    sql TEXT NOT NULL, level TEXT NOT NULL, last_value TEXT, last_run_at TEXT NOT NULL,
    changed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ask_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ask_id TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_ask ON ask_events(ask_id);
"""

#: Columns added after the first release. Old app.db files get them on open.
_ADDED_COLUMNS = {
    "asks": [("user_id", "TEXT")],
    "review_items": [("user_id", "TEXT")],
}

#: Ledger kinds. "ask" and "arena" spend credits; the rest are the provider's
#: changes and refunds.
SPEND_KINDS = ("ask", "arena")


class EmailTaken(Exception):
    pass


class NotEnoughCredits(Exception):
    pass


def _public_user(row: dict | None) -> dict | None:
    """A user as the API shows it: never the password hash."""
    if row is None:
        return None
    return {
        "id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"],
        "active": bool(row["active"]), "created_at": row["created_at"],
    }

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
            for table, cols in _ADDED_COLUMNS.items():
                have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
                for name, typ in cols:
                    if name not in have:
                        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")

    # -- plumbing ----------------------------------------------------------

    @contextmanager
    def _tx(self):
        """One write transaction that holds the write lock from its start.

        BEGIN IMMEDIATE makes a second writer wait, so a balance read inside
        the transaction cannot be changed by another request before the
        transaction writes the new balance.
        """
        con = self._connect()
        con.isolation_level = None
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

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

    @staticmethod
    def _insert_ask(con: sqlite3.Connection, response: dict, user_id: str | None) -> None:
        con.execute(
            "INSERT INTO asks (id, database_id, question, model, level, answer_text, response,"
            " latency_ms, created_at, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                response["ask_id"], response["database_id"], response["question"],
                response["model"], response["level"], response.get("answer_text"),
                _dump(response), int(response.get("latency_ms", 0)), response["created_at"],
                user_id,
            ),
        )
        con.execute(
            "INSERT INTO ask_events (ask_id, actor, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (response["ask_id"], "verdict", "asked", f"Level: {response['level']}", response["created_at"]),
        )

    def save_ask(self, response: dict, user_id: str | None = None) -> None:
        """Save one full /api/ask response. ``response['ask_id']`` is the key."""
        with self._tx() as con:
            self._insert_ask(con, response, user_id)

    def save_ask_and_charge(self, response: dict, user_id: str, price: int) -> dict | None:
        """Save the ask and charge for it in one transaction.

        Raises NotEnoughCredits (and saves nothing) if the balance is below
        ``price``. Returns the ledger row, or None when the price is 0.
        """
        with self._tx() as con:
            self._insert_ask(con, response, user_id)
            if price <= 0:
                return None
            return self._ledger_write(
                con, user_id, "ask", -price, ask_id=response["ask_id"], question=response["question"]
            )

    def get_ask(self, ask_id: str) -> dict | None:
        row = self._one("SELECT * FROM asks WHERE id = ?", (ask_id,))
        if row is None:
            return None
        resp = row["response"]
        resp["flagged"] = bool(row["flagged"])
        resp["flag_note"] = row["flag_note"]
        return resp

    def ask_owner(self, ask_id: str) -> tuple[bool, str | None]:
        """(exists, user_id) for one ask."""
        row = self._one("SELECT user_id FROM asks WHERE id = ?", (ask_id,))
        return (row is not None, row["user_id"] if row else None)

    def list_asks(
        self, limit: int = 20, database_id: str | None = None, user_id: str | None = None
    ) -> list[dict]:
        """``user_id`` None means every user's asks (the provider's view)."""
        conds, args = [], []
        if database_id:
            conds.append("database_id = ?")
            args.append(database_id)
        if user_id:
            conds.append("user_id = ?")
            args.append(user_id)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
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

    def count_asks_since(self, since: str, user_id: str | None = None) -> dict[str, int]:
        sql, args = "SELECT level, COUNT(*) AS n FROM asks WHERE created_at >= ?", [since]
        if user_id:
            sql += " AND user_id = ?"
            args.append(user_id)
        rows = self._all(sql + " GROUP BY level", tuple(args))
        return {r["level"]: r["n"] for r in rows}

    # -- ask history (the event log of one ask) -------------------------------

    def add_event(self, ask_id: str, actor: str, action: str, detail: str | None = None) -> None:
        self._run(
            "INSERT INTO ask_events (ask_id, actor, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (ask_id, actor, action, detail, now()),
        )

    def list_events(self, ask_id: str) -> list[dict]:
        return self._all(
            "SELECT actor, action, detail, created_at FROM ask_events WHERE ask_id = ? ORDER BY id",
            (ask_id,),
        )

    # -- review queue --------------------------------------------------------

    def add_review_item(self, ask_id: str, source: str = "auto") -> dict:
        item_id = new_id("r")
        self._run(
            "INSERT INTO review_items (id, ask_id, source, status, created_at, user_id)"
            " SELECT ?, ?, ?, 'open', ?, user_id FROM asks WHERE id = ?",
            (item_id, ask_id, source, now(), ask_id),
        )
        return self.get_review_item(item_id)

    def get_review_item(self, item_id: str) -> dict | None:
        return self._one("SELECT * FROM review_items WHERE id = ?", (item_id,))

    def open_item_for_ask(self, ask_id: str) -> dict | None:
        return self._one(
            "SELECT * FROM review_items WHERE ask_id = ? AND status = 'open'", (ask_id,)
        )

    def list_review_items(
        self, status: str | None = None, level: str | None = None, database_id: str | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        sql = (
            "SELECT r.*, a.question, a.level, a.database_id, a.response FROM review_items r"
            " JOIN asks a ON a.id = r.ask_id WHERE 1 = 1"
        )
        args: list = []
        for col, val in (("r.status", status), ("a.level", level), ("a.database_id", database_id),
                         ("r.user_id", user_id)):
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

    def review_counts(self, user_id: str | None = None) -> dict[str, int]:
        sql, args = (
            "SELECT a.level, COUNT(*) AS n FROM review_items r JOIN asks a ON a.id = r.ask_id"
            " WHERE r.status = 'open'", [],
        )
        if user_id:
            sql += " AND r.user_id = ?"
            args.append(user_id)
        rows = self._all(sql + " GROUP BY a.level", tuple(args))
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

    # -- users and sessions ----------------------------------------------------

    def create_user(
        self, name: str, email: str, password_hash: str, role: str = "analyst",
        start_credits: int = 0,
    ) -> dict:
        """Create an account. Starting credits are a 'grant' row, like any other change.

        Raises EmailTaken if the email exists (case ignored).
        """
        uid = new_id("u")
        with self._tx() as con:
            try:
                con.execute(
                    "INSERT INTO users (id, name, email, password_hash, role, active, balance, created_at)"
                    " VALUES (?, ?, ?, ?, ?, 1, 0, ?)",
                    (uid, name.strip(), email.strip(), password_hash, role, now()),
                )
            except sqlite3.IntegrityError:
                raise EmailTaken(email) from None
            if start_credits > 0:
                self._ledger_write(con, uid, "grant", start_credits, note="Starting credits")
        return self.get_user(uid)

    def get_user(self, user_id: str) -> dict | None:
        return _public_user(self._one("SELECT * FROM users WHERE id = ?", (user_id,)))

    def user_login_row(self, email: str) -> dict | None:
        """The full row, with the password hash. Only for checking a login."""
        return self._one("SELECT * FROM users WHERE email = ?", (email.strip(),))

    def set_active(self, user_id: str, active: bool) -> None:
        with self._tx() as con:
            con.execute("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))
            if not active:
                con.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def create_session(self, user_id: str, token_hash: str, ttl_hours: float) -> None:
        expires = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat(timespec="seconds")
        self._run(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, now(), expires),
        )

    def session_user(self, token_hash: str) -> dict | None:
        """The user behind a token, or None if the token is unknown or expired."""
        row = self._one(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id"
            " WHERE s.token_hash = ? AND s.expires_at > ?",
            (token_hash, now()),
        )
        return _public_user(row)

    def delete_session(self, token_hash: str) -> None:
        self._run("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    # -- credits -----------------------------------------------------------------

    @staticmethod
    def _ledger_write(
        con: sqlite3.Connection, user_id: str, kind: str, amount: int,
        ask_id: str | None = None, question: str | None = None, note: str | None = None,
    ) -> dict:
        """Change a balance and write its ledger row. Must run inside _tx().

        The cached users.balance and the ledger row change in the same
        transaction, so the balance always equals the sum of the ledger.
        """
        row = con.execute("SELECT balance FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise KeyError(user_id)
        after = row[0] + amount
        if after < 0:
            raise NotEnoughCredits(f"balance {row[0]}, change {amount}")
        entry = {
            "id": new_id("l"), "at": now(), "kind": kind, "amount": amount, "balance_after": after,
            "ask_id": ask_id, "question": question, "note": note,
        }
        con.execute("UPDATE users SET balance = ? WHERE id = ?", (after, user_id))
        con.execute(
            "INSERT INTO credit_ledger (id, user_id, at, kind, amount, balance_after, ask_id, question, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry["id"], user_id, entry["at"], kind, amount, after, ask_id, question, note),
        )
        return entry

    def change_credits(
        self, user_id: str, kind: str, amount: int, note: str | None = None,
        ask_id: str | None = None, question: str | None = None,
    ) -> dict:
        """Raises NotEnoughCredits if the balance would go below 0, KeyError for an unknown user."""
        with self._tx() as con:
            return self._ledger_write(con, user_id, kind, amount, ask_id, question, note)

    def balance(self, user_id: str) -> int:
        row = self._one("SELECT balance FROM users WHERE id = ?", (user_id,))
        return row["balance"] if row else 0

    def credit_summary(self, user_id: str) -> dict:
        month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
        kinds = ",".join("?" * len(SPEND_KINDS))
        row = self._one(
            "SELECT COALESCE(-SUM(amount), 0) AS total,"
            " COALESCE(-SUM(CASE WHEN at >= ? THEN amount ELSE 0 END), 0) AS month"
            f" FROM credit_ledger WHERE user_id = ? AND kind IN ({kinds})",
            (month_start, user_id, *SPEND_KINDS),
        )
        return {"balance": self.balance(user_id), "used_total": row["total"], "used_this_month": row["month"]}

    def ledger(self, user_id: str, limit: int = 500) -> list[dict]:
        return self._all(
            "SELECT id, at, kind, amount, balance_after, ask_id, question, note FROM credit_ledger"
            " WHERE user_id = ? ORDER BY at DESC, rowid DESC LIMIT ?",
            (user_id, int(limit)),
        )

    def admin_user_rows(self, user_id: str | None = None) -> list[dict]:
        """Every account with its balance and use, for the provider panel."""
        kinds = ",".join("?" * len(SPEND_KINDS))
        sql = (
            "SELECT u.*,"
            " (SELECT COALESCE(-SUM(amount), 0) FROM credit_ledger l"
            f"   WHERE l.user_id = u.id AND l.kind IN ({kinds})) AS used_total,"
            " (SELECT COUNT(*) FROM asks a WHERE a.user_id = u.id) AS asks_count,"
            " (SELECT MAX(at) FROM credit_ledger l"
            f"   WHERE l.user_id = u.id AND l.kind IN ({kinds})) AS last_active_at"
            " FROM users u"
        )
        args: list = [*SPEND_KINDS, *SPEND_KINDS]
        if user_id:
            sql += " WHERE u.id = ?"
            args.append(user_id)
        rows = self._all(sql + " ORDER BY u.created_at, u.rowid", tuple(args))
        return [
            {**_public_user(r), "balance": r["balance"], "used_total": r["used_total"],
             "asks_count": r["asks_count"], "last_active_at": r["last_active_at"]}
            for r in rows
        ]

    # -- saved answers -------------------------------------------------------------

    @staticmethod
    def _saved_json(r: dict | None) -> dict | None:
        if r is None:
            return None
        return {
            "id": r["id"], "ask_id": r["ask_id"], "name": r["name"], "sql": r["sql"],
            "level": r["level"], "last_value": r["last_value"], "last_run_at": r["last_run_at"],
            "changed": bool(r["changed"]),
        }

    def add_saved(self, user_id: str, ask: dict, name: str) -> dict:
        sid = new_id("s")
        self._run(
            "INSERT INTO saved (id, user_id, ask_id, name, sql, level, last_value, last_run_at,"
            " changed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (sid, user_id, ask["ask_id"], name.strip(), ask.get("sql") or "", ask["level"],
             ask.get("answer_text"), ask["created_at"], now()),
        )
        return self.get_saved(sid)

    def get_saved(self, saved_id: str, user_id: str | None = None) -> dict | None:
        sql, args = "SELECT * FROM saved WHERE id = ?", [saved_id]
        if user_id:
            sql += " AND user_id = ?"
            args.append(user_id)
        return self._saved_json(self._one(sql, tuple(args)))

    def list_saved(self, user_id: str | None = None) -> list[dict]:
        if user_id:
            rows = self._all(
                "SELECT * FROM saved WHERE user_id = ? ORDER BY created_at DESC, rowid DESC", (user_id,)
            )
        else:
            rows = self._all("SELECT * FROM saved ORDER BY created_at DESC, rowid DESC")
        return [self._saved_json(r) for r in rows]

    def delete_saved(self, saved_id: str, user_id: str | None = None) -> bool:
        sql, args = "DELETE FROM saved WHERE id = ?", [saved_id]
        if user_id:
            sql += " AND user_id = ?"
            args.append(user_id)
        return self._run(sql, tuple(args)) > 0

    def update_saved_run(self, saved_id: str, ask: dict) -> dict | None:
        """Point a saved answer at a fresh run, and note whether the answer changed."""
        old = self.get_saved(saved_id)
        new_value = ask.get("answer_text")
        changed = old is not None and (old["last_value"] != new_value or old["level"] != ask["level"])
        self._run(
            "UPDATE saved SET ask_id = ?, sql = ?, level = ?, last_value = ?, last_run_at = ?,"
            " changed = ? WHERE id = ?",
            (ask["ask_id"], ask.get("sql") or "", ask["level"], new_value, ask["created_at"],
             int(changed), saved_id),
        )
        return self.get_saved(saved_id)
