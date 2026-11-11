"""Categories for why a gold query failed, derived from the verifier status and SQLite's message."""

from collections import Counter
from enum import Enum


class AnnotationError(Enum):
    OK = "ok"
    SYNTAX_ERROR = "syntax_error"
    MISSING_TABLE = "missing_table"
    MISSING_COLUMN = "missing_column"
    MISSING_DATABASE = "missing_database"
    OTHER_ERROR = "other_error"  # an SQL error that matches no known pattern
    TIMEOUT = "timeout"
    BLOCKED_QUERY = "blocked_query"
    CRASHED = "crashed"  # a defect in the verifier, not in the query


_BY_STATUS = {
    "ok": AnnotationError.OK,
    "timeout": AnnotationError.TIMEOUT,
    "blocked": AnnotationError.BLOCKED_QUERY,
    "crashed": AnnotationError.CRASHED,
}

# Checked in order. The specific messages come before "syntax error" so that,
# e.g., a column named "nearby" is not mistaken for a syntax error.
_ERROR_PATTERNS = (
    ("no such table", AnnotationError.MISSING_TABLE),
    ("no such column", AnnotationError.MISSING_COLUMN),
    ("unable to open", AnnotationError.MISSING_DATABASE),
    ("cannot open", AnnotationError.MISSING_DATABASE),
    ("syntax error", AnnotationError.SYNTAX_ERROR),
    ("incomplete input", AnnotationError.SYNTAX_ERROR),
)


def categorize_error(status: str, error_msg: str | None = None) -> AnnotationError:
    """Map an ExecutionResult status (and, for "error", its message) to a category."""
    if status in _BY_STATUS:
        return _BY_STATUS[status]
    msg = (error_msg or "").lower()
    for pattern, category in _ERROR_PATTERNS:
        if pattern in msg:
            return category
    return AnnotationError.OTHER_ERROR


def summarize_errors(audit_results: list[dict]) -> dict[str, int]:
    """Count audit results per category, e.g. ``{"missing_table": 1, "ok": 2}``."""
    counts = Counter(
        categorize_error(r["status"], r.get("error_msg")).value for r in audit_results
    )
    return dict(sorted(counts.items()))
