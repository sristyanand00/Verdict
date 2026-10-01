"""Result types returned by the verifier.

Failure is a returned value, never an exception. During training the verifier
runs millions of queries and most of them fail, so a single malformed
completion must not be able to stop a long GPU run.

Both classes are frozen so a verdict cannot be modified after it is produced;
the benchmark audit counts depend on that. Rows are tuples rather than lists so
they stay hashable, which keeps the unordered comparison in compare.py simple.
"""

from dataclasses import dataclass
from typing import Literal

#: Outcome of running one query. The statuses are kept separate because the
#: audit reports them separately.
#:   ok      - the query ran
#:   blocked - the query was refused as unsafe
#:   timeout - the query exceeded its time limit and was stopped
#:   error   - the SQL is invalid (bad table, syntax error)
#:   crashed - an unexpected failure inside the verifier itself
Status = Literal["ok", "blocked", "timeout", "error", "crashed"]


@dataclass(frozen=True)
class ExecutionResult:
    """One query, run once, against one database."""

    status: Status
    rows: tuple[tuple, ...] = ()
    columns: tuple[str, ...] = ()
    error: str | None = None
    elapsed_ms: float = 0.0
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class VerificationResult:
    """A candidate query judged against the gold answer.

    ``reason`` records why the verdict was reached. When the gold query itself
    fails, the reason says so; counting those cases is the benchmark audit.
    """

    verdict: Literal["correct", "wrong", "invalid"]
    candidate: ExecutionResult
    gold: ExecutionResult | None = None
    reason: str = ""
