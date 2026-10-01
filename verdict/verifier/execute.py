"""Run one SQL query against one SQLite database, in-process.

This is the fast path used during training. It is protected by the safety
layers in safety.py and stopped by an in-process deadline. pool.py provides a
slower path that runs the query in a separate, killable process.
"""

import sqlite3
import time
from pathlib import Path

from verdict.verifier.safety import looks_dangerous, open_safe_connection
from verdict.verifier.types import ExecutionResult

#: Upper bound on rows read into memory. A model can write a join that returns
#: millions of rows; 10,000 is well above the size of any BIRD gold answer.
MAX_ROWS = 10_000


def execute_query(
    sql: str,
    db_path: str | Path,
    timeout_s: float = 5.0,
    use_first_pass_filter: bool = True,
) -> ExecutionResult:
    """Run ``sql`` against the database at ``db_path``.

    Never raises; every outcome is returned as an ExecutionResult.

    ``use_first_pass_filter=False`` disables the keyword pre-filter. Tests use
    it to show that the read-only connection and the authorizer block every
    attack on their own. Gold SQL also skips it, since gold queries are trusted
    and must not be rejected by a false positive.
    """
    start = time.perf_counter()

    def ms() -> float:
        return (time.perf_counter() - start) * 1000

    if use_first_pass_filter and looks_dangerous(sql):
        return ExecutionResult(
            status="blocked", error="rejected by first-pass keyword filter", elapsed_ms=ms()
        )

    con = None
    try:
        con = open_safe_connection(db_path, timeout_s=timeout_s)
        cur = con.cursor()
        cur.execute(sql)

        # cur.description is None for statements that return no result set.
        columns = tuple(d[0] for d in cur.description) if cur.description else ()
        rows = tuple(cur.fetchmany(MAX_ROWS))
        truncated = len(rows) == MAX_ROWS and cur.fetchone() is not None

        return ExecutionResult(
            status="ok", rows=rows, columns=columns, elapsed_ms=ms(), truncated=truncated
        )

    except sqlite3.DatabaseError as e:
        msg = str(e)
        if "interrupted" in msg:
            return ExecutionResult(
                status="timeout", error=f"deadline of {timeout_s}s exceeded", elapsed_ms=ms()
            )
        # SQLite reports a refused operation with different messages:
        #   "not authorized"       authorizer, most actions
        #   "authorization denied" authorizer, e.g. VACUUM
        #   "readonly"             the read-only connection refused a write
        # Missing one would record an attack as an ordinary SQL error and
        # distort the audit counts.
        denied = any(w in msg for w in ("not authorized", "authorization denied", "readonly"))
        return ExecutionResult(
            status="blocked" if denied else "error",
            error=f"{type(e).__name__}: {msg}",
            elapsed_ms=ms(),
        )
    except sqlite3.Error as e:
        return ExecutionResult(status="error", error=f"{type(e).__name__}: {e}", elapsed_ms=ms())
    except Exception as e:
        # A defect in the verifier rather than in the query.
        return ExecutionResult(status="crashed", error=f"{type(e).__name__}: {e}", elapsed_ms=ms())
    finally:
        # Always release the connection; leaked handles accumulate quickly at
        # training volume.
        if con is not None:
            con.close()
