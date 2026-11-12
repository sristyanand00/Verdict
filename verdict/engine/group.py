"""Step 3 of the trust engine: run every attempt and group matching answers.

    run_and_group(attempts, db_path) -> Grouping

Two attempts land in the same group when their results are the same, even if
their SQL is different:

    SELECT SUM(amount) FROM sales WHERE city = 'Pune'           -> 150000
    SELECT TOTAL(amount) FROM sales WHERE LOWER(city) = 'pune'  -> 150000.0
    => same group, because the answer is what the user sees, not the SQL.

"Same" is decided by the verifier's compare_results, the same function that
scores training rewards, so 94 equals 94.0, NULL differs from 0, and column
order is ignored.

Each query runs in its own child process (verifier/pool.py) that is killed if
it runs too long. That is slower than running in-process, but a user's request
must never hang on a runaway query written by the AI.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from verdict.engine.generate import Attempt
from verdict.verifier.compare import compare_results, gold_has_order_by
from verdict.verifier.pool import execute_isolated
from verdict.verifier.types import ExecutionResult

#: Per-query time limit. Questions on an uploaded spreadsheet should take
#: milliseconds; anything slower is almost certainly a bad join.
QUERY_TIMEOUT_S = 5.0

#: Queries run side by side, each in its own process. Starting many
#: processes at once can fail on Windows, so at most this many at a time.
MAX_PARALLEL_RUNS = 4

#: compare_results decides row order from a "gold" SQL string. Passing a query
#: without ORDER BY makes it compare rows as a multiset.
_UNORDERED = "SELECT 1"


@dataclass
class AnswerGroup:
    """Attempts that produced the same result."""

    result: ExecutionResult
    #: indexes into the attempts list
    members: list[int] = field(default_factory=list)
    #: the SQL of each member, in the same order
    sqls: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def is_empty_answer(self) -> bool:
        """True when the answer says nothing: no rows, or only NULLs.

        SUM over zero matching rows returns one row holding NULL, so a filter
        on a misspelled value ("pune" instead of "Pune") looks like this.
        """
        rows = self.result.rows
        return not rows or all(v is None for row in rows for v in row)


@dataclass
class Grouping:
    """Everything that happened to the n attempts."""

    n_attempts: int
    groups: list[AnswerGroup]          # largest first
    n_cannot_answer: int
    n_failed: int                      # empty reply, or SQL that did not run
    results: list[ExecutionResult | None]  # per attempt; None if no SQL was run

    @property
    def top(self) -> AnswerGroup | None:
        return self.groups[0] if self.groups else None


def _same_answer(a: AnswerGroup, sql: str, result: ExecutionResult) -> bool:
    # Row order counts only when both queries asked for an order.
    rep_sql = a.sqls[0]
    order_sql = rep_sql if gold_has_order_by(rep_sql) and gold_has_order_by(sql) else _UNORDERED
    return compare_results(result, a.result, order_sql).verdict == "correct"


def run_and_group(
    attempts: list[Attempt], db_path: str | Path, timeout_s: float = QUERY_TIMEOUT_S
) -> Grouping:
    """Run every SQL attempt against ``db_path`` and group equal results."""
    sql_idx = [i for i, a in enumerate(attempts) if a.kind == "sql"]

    # Each run starts its own process, so running them side by side cuts the
    # wait from roughly 8x to roughly 1x.
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_RUNS) as pool:
        ran = list(pool.map(lambda i: execute_isolated(attempts[i].sql, db_path, timeout_s), sql_idx))

    results: list[ExecutionResult | None] = [None] * len(attempts)
    for i, r in zip(sql_idx, ran):
        results[i] = r

    groups: list[AnswerGroup] = []
    n_failed = sum(1 for a in attempts if a.kind == "empty")
    for i in sql_idx:
        r = results[i]
        if not r.ok:
            n_failed += 1
            continue
        for g in groups:
            if _same_answer(g, attempts[i].sql, r):
                g.members.append(i)
                g.sqls.append(attempts[i].sql)
                break
        else:
            groups.append(AnswerGroup(result=r, members=[i], sqls=[attempts[i].sql]))

    # Largest group first; on a tie the group seen first wins, which keeps
    # the output stable for the same input.
    groups.sort(key=lambda g: -g.size)
    return Grouping(
        n_attempts=len(attempts),
        groups=groups,
        n_cannot_answer=sum(1 for a in attempts if a.kind == "cannot_answer"),
        n_failed=n_failed,
        results=results,
    )
