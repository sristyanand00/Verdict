"""Execution safety: read-only connection, authorizer, keyword pre-filter, deadline.

The security controls are the read-only URI (``mode=ro``) and the authorizer
callback. Both act inside SQLite, so they catch writes wherever they appear in
the statement, including inside CTEs and subqueries. The keyword filter is only
a cheap pre-filter that avoids opening a connection for obviously invalid input;
it is not relied on for safety.
"""

import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

# Layer 1: keyword pre-filter. Cheap, and known to produce false positives.
_BANNED = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|REPLACE|TRUNCATE|"
    r"ATTACH|DETACH|VACUUM|REINDEX|PRAGMA)\b",
    re.IGNORECASE,
)


def looks_dangerous(sql: str) -> bool:
    return bool(_BANNED.search(sql or ""))


# Layer 2: the SQLite driver refuses to open a writable handle.
def read_only_uri(db_path: str | Path, immutable: bool = True) -> str:
    """Build ``file:///C:/path/db.sqlite?mode=ro``.

    SQLite URIs need forward slashes and a leading slash. ``quote`` escapes
    spaces in the path but leaves ``/`` and ``:`` intact. ``immutable=1`` skips
    locking and is only safe for files that no other process writes to, such
    as the static benchmark databases.
    """
    p = Path(db_path).resolve().as_posix()
    if not p.startswith("/"):
        p = "/" + p
    uri = "file://" + quote(p, safe="/:")
    return uri + ("?mode=ro&immutable=1" if immutable else "?mode=ro")


# Layer 3: SQLite consults the authorizer for every operation while compiling
# the statement, so a write anywhere in the statement is refused before any
# data is touched.
_ALLOWED = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


def strict_authorizer(action, arg1, arg2, db_name, trigger_name):
    if action in _ALLOWED:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


# In-process deadline. SQLite calls the handler every `check_every` VM
# instructions; returning 1 aborts the statement with "interrupted".
# 1000 balances Python call overhead against how long a tight loop can run
# between checks.
def attach_deadline(con: sqlite3.Connection, timeout_s: float, check_every: int = 1000) -> None:
    deadline = time.perf_counter() + timeout_s
    con.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, check_every)


def open_safe_connection(
    db_path: str | Path, timeout_s: float | None = 5.0, immutable: bool = True
) -> sqlite3.Connection:
    """Open a read-only connection with the authorizer and deadline attached."""
    con = sqlite3.connect(read_only_uri(db_path, immutable), uri=True)
    con.set_authorizer(strict_authorizer)
    if timeout_s is not None:
        attach_deadline(con, timeout_s)
    return con
