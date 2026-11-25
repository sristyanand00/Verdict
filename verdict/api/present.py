"""Turn engine objects into the JSON the frontend reads (docs/API.md)."""

from __future__ import annotations

import base64
import math

from verdict.engine.ask import Answer
from verdict.engine.lineage import lineage
from verdict.verifier.types import ExecutionResult

#: Rows sent in one response. The verifier keeps up to 10,000; a table that
#: long is not readable on screen, and the evidence view only needs a preview.
MAX_ROWS = 500
PREVIEW_ROWS = 5


def json_value(v):
    """Make one SQLite value safe for JSON."""
    if isinstance(v, bytes):
        return "base64:" + base64.b64encode(v).decode("ascii")
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def json_rows(rows, limit: int = MAX_ROWS) -> list[list]:
    return [[json_value(v) for v in row] for row in list(rows)[:limit]]


def format_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.0f}" if v.is_integer() else f"{v:,.2f}"
    return str(v)


def answer_text(columns, rows) -> str | None:
    """One line for the answer card: the value itself, or the row count."""
    if not columns:
        return None
    if len(rows) == 1 and len(columns) == 1:
        return format_value(rows[0][0])
    if len(rows) == 1:
        return ", ".join(f"{c}: {format_value(v)}" for c, v in zip(columns, rows[0]))
    return f"{len(rows):,} rows"


def result_json(r: ExecutionResult) -> dict:
    return {
        "status": r.status,
        "columns": list(r.columns),
        "rows": json_rows(r.rows),
        "row_count": len(r.rows),
        "truncated": r.truncated or len(r.rows) > MAX_ROWS,
        "error": r.error,
        "elapsed_ms": round(r.elapsed_ms, 1),
    }


def ask_response(
    a: Answer, *, ask_id: str, database_id: str, model_id: str, model_label: str,
    latency_ms: int, created_at: str, tested_trust: dict | None,
) -> dict:
    g = a.grouping
    group_of = {i: gi for gi, grp in enumerate(g.groups) for i in grp.members}

    attempts = []
    for i, att in enumerate(a.attempts):
        r = g.results[i] if i < len(g.results) else None
        attempts.append({
            "index": i,
            "kind": att.kind,                         # sql, cannot_answer, empty
            "sql": att.sql or None,
            "status": r.status if r is not None else None,
            "error": (r.error or None) if r is not None and not r.ok else None,
            "group": group_of.get(i),                 # index into groups, or null
        })

    not_in_data = any(r.code == "not_in_data" for r in a.reasons)
    return {
        "ask_id": ask_id,
        "question": a.question,
        "database_id": database_id,
        "level": a.verdict,
        "reasons": [{"code": r.code, "text": r.text} for r in a.reasons],
        "answer_text": answer_text(a.columns, a.rows) if a.sql else None,
        "columns": list(a.columns),
        "rows": json_rows(a.rows),
        "row_count": len(a.rows),
        "sql": a.sql or None,
        "groups": [
            {
                "size": grp.size,
                "sql": grp.sqls[0],
                "columns": list(grp.result.columns),
                "preview": json_rows(grp.result.rows, PREVIEW_ROWS),
                "row_count": len(grp.result.rows),
                "empty": grp.is_empty_answer,
            }
            for grp in g.groups
        ],
        "attempts": attempts,
        "n_attempts": g.n_attempts,
        "n_cannot_answer": g.n_cannot_answer,
        "n_failed": g.n_failed,
        "checks": [c.to_dict() for c in a.checks],
        "options": None if a.options is None else [
            {
                "label": o.label, "sql": o.sql, "columns": list(o.columns),
                "rows": json_rows(o.rows), "size": o.size,
                "answer_text": answer_text(o.columns, o.rows),
            }
            for o in a.options
        ],
        "missing": a.missing,
        "tables_available": a.tables if not_in_data else None,
        "knowledge_used": a.knowledge_used,
        "lineage": lineage(a.sql) if a.sql else None,
        "tested_trust": tested_trust,
        "agreement_level": a.level,
        "model": model_id,
        "model_label": model_label,
        "latency_ms": latency_ms,
        "created_at": created_at,
        "review_id": None,
        "flagged": False,
        "flag_note": None,
    }
